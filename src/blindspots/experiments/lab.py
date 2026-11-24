"""Experiment 1 ("in the lab"): plant faults in a five-agent chain and compare six guard configurations.

    conversation -> 1 intake -> 2 verifier -> 3 pricing -> 4 policy -> planner -> final action
                  hand-off 1   hand-off 2   hand-off 3   hand-off 4

Only the intake agent sees the conversation; the others see the hand-off and, where their job needs it, the
order records. For each case:
  * the clean chain runs once, and every hand-off and the final action get all three checks (code/source/local);
  * for each fault level and position, the clean hand-offs up to that position are reused, the fault is planted
    in that hand-off, and the rest of the chain and its checks are rerun;
  * a "confirmed" fault is planted in the conversation, so the whole chain is rerun;
  * every config in `guards.CONFIGS` is scored on the same logged runs.

Writes <out>/lab_results.csv (one row per run, with each config's verdict) and <out>/lab_traces.jsonl (every
hand-off and every check's verdict and explanation).
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import random
from pathlib import Path
from typing import Any

from blindspots import prompts
from blindspots.faults import HANDOFF_LEVELS, Handoff, confirmed_case, correct_handoff, inject
from blindspots.guards import CONFIGS, KINDS, check, score
from blindspots.llm import LLM, PROVIDERS
from blindspots.runner import over_budget, parallel_map, write_csv, write_jsonl
from blindspots.tau2 import (
    DEFAULT_TAU2_DIR,
    HANDOFF_FIELDS,
    WRITE_TOOLS,
    LabCase,
    build_lab_cases,
    norm,
    policy_text,
    records_only,
    same_action,
)

log = logging.getLogger(__name__)
N_HOPS = 4
NOTE_KEYS = ("verifier_note", "pricing_note", "policy_note")


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tau2-dir", type=Path, default=DEFAULT_TAU2_DIR)
    p.add_argument("--n", type=int, default=58, help="number of cases (58 is every qualifying task)")
    p.add_argument("--provider", default="anthropic", choices=PROVIDERS)
    p.add_argument("--agent-model", default="claude-haiku-5-5")
    p.add_argument("--checker-provider", default=None, choices=PROVIDERS, help="defaults to --provider")
    p.add_argument("--checker-model", default=None, help="defaults to --agent-model")
    p.add_argument("--positions", default="1,2,4", help="hand-offs to plant faults in (1 = after intake)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--max-failures", type=int, default=10, help="stop after this many failed API calls")
    p.add_argument("--out", type=Path, default=Path("results/lab"))
    p.add_argument("--dry-run", action="store_true", help="stub replies, no API calls")


# ------------------------------------------------------------------------------------------------- the chain


def intake(agent: LLM, case: LabCase, transcript: str | None = None) -> Handoff:
    h = agent.ask_json(prompts.INTAKE, transcript or case.transcript, stub=correct_handoff(case)).data
    if h.get("action") != "cancel_pending_order":
        h["reason"] = None  # only cancellations take a reason
    return h


def run_chain(
    agent: LLM, case: LabCase, policy: str, hops: list[Handoff], start: int, notes: list[dict[str, Any]] | None = None
) -> tuple[list[Handoff], dict[str, Any], list[dict[str, Any]]]:
    """Run agents `start`..4 and the planner. `hops` holds the hand-offs before `start`.

    Each agent's free-text note goes to the trace only, never to the next agent: a note repeating the original IDs
    would give a planted fault away, and real pipelines usually pass structured fields between agents.
    """
    hops = copy.deepcopy(hops)
    notes = list(notes or [{} for _ in hops])
    records = records_only(case.transcript)
    for n in range(start, N_HOPS + 1):
        prev = hops[-1]
        if n == 2:
            out = agent.ask_json(
                prompts.VERIFIER,
                f"RECORDS:\n{records}\n\nHANDOFF:\n{json.dumps(prev)}",
                stub={**prev, "ownership_ok": True, "verifier_note": "dry run"},
            ).data
        elif n == 3:
            out = agent.ask_json(
                prompts.PRICING,
                f"RECORDS:\n{records}\n\nHANDOFF:\n{json.dumps(prev)}",
                stub={**prev, "price_difference": None, "pricing_note": "dry run"},
            ).data
        else:
            d = agent.ask_json(
                prompts.POLICY,
                f"POLICY:\n{policy}\n\nHANDOFF:\n{json.dumps(prev)}",
                stub={"allowed": True, "note": "dry run"},
            ).data
            out = {**prev, "policy_allowed": d.get("allowed"), "policy_note": d.get("note")}
        notes.append({k: out.pop(k) for k in NOTE_KEYS if k in out})
        hops.append(out)
    last = hops[-1]
    stub = {
        "name": last.get("action"),
        "arguments": {
            k: last[k] for k in HANDOFF_FIELDS if k in case.correct_action["arguments"] and last.get(k) is not None
        },
    }
    final = agent.ask_json(prompts.PLANNER, f"HANDOFF:\n{json.dumps(last)}", stub=stub).data or {}
    return hops, final, notes


def run_checks(
    checker: LLM,
    transcript: str,
    hops: list[Handoff],
    final: dict[str, Any],
    start: int,
    reuse: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> dict[str, Any]:
    """All three checks at hand-offs `start`..4 and at the final action. Earlier hops reuse the clean verdicts."""
    trace_hops = [
        {
            "hop": i + 1,
            "handoff": h,
            "notes": notes[i] if i < len(notes) else {},
            "checks": reuse[i] if i + 1 < start else {k: check(checker, k, h, transcript) for k in KINDS},
        }
        for i, h in enumerate(hops)
    ]
    final_checks = {k: check(checker, k, final, transcript, is_action=True) for k in KINDS}
    return {"hops": trace_hops, "final": {"action": final, "checks": final_checks}}


def carries_correct_change(handoff: Handoff, case: LabCase) -> bool:
    """Does this hand-off still describe the correct change? Compares only the fields the correct action uses."""
    a = case.correct_action
    return handoff.get("action") == a["name"] and norm({k: handoff.get(k) for k in a["arguments"]}) == norm(
        a["arguments"]
    )


def _score_row(row: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    for c in CONFIGS:
        row[f"{c}_flag"], row[f"{c}_where"], row[f"{c}_calls"], cost = score(trace, c)
        row.update({f"{c}_{k}": v for k, v in cost.items()})
    return row


# ------------------------------------------------------------------------------------------------ experiment


def run(a: argparse.Namespace) -> None:
    positions = [int(x) for x in a.positions.split(",")]
    out = Path("results/dry-run/lab") if a.dry_run else a.out
    policy = policy_text(a.tau2_dir)
    cases = build_lab_cases(a.tau2_dir, a.n, a.seed)
    agent = LLM(a.provider, a.agent_model, a.dry_run)
    checker = LLM(a.checker_provider or a.provider, a.checker_model or a.agent_model, a.dry_run)
    models = (agent, checker)
    log.info(
        "%d cases | positions %s | agents %s | checker %s%s",
        len(cases),
        positions,
        agent,
        checker,
        " | DRY RUN" if a.dry_run else "",
    )

    def clean(case: LabCase) -> dict[str, Any] | None:
        if over_budget(models, a.max_failures):
            return None
        hops, final, notes = run_chain(agent, case, policy, [intake(agent, case)], 2)
        trace = run_checks(checker, case.transcript, hops, final, 1, [], notes)
        log.info("clean     %-40s final correct=%s", case.case_id, same_action(final, case.correct_action))
        return {"case": case, "hops": hops, "notes": notes, "trace": trace}

    base = parallel_map(clean, cases, a.workers)

    def faulted(job: tuple[dict[str, Any], str, int]) -> dict[str, Any] | None:
        b, level, pos = job
        if over_budget(models, a.max_failures):
            return None
        case: LabCase = b["case"]
        rng = random.Random(f"{a.seed}-{case.case_id}-{level}-{pos}")
        head = {"case_id": case.case_id, "level": level, "position": pos}
        if level == "confirmed":
            fcase, fault = confirmed_case(case, rng)
            if fcase is None:
                return {**head, "applied": False, "fault": fault}
            h1 = intake(agent, case, fcase.transcript)
            hops, final, notes = run_chain(agent, fcase, policy, [h1], 2)
            trace = run_checks(checker, fcase.transcript, hops, final, 1, [], notes)
            took = not carries_correct_change(h1, case)  # did intake adopt the wrong read-back?
        else:
            bad, fault = inject(b["hops"][pos - 1], case, level, rng)
            if bad is None:
                return {**head, "applied": False, "fault": fault}
            hops, final, notes = run_chain(agent, case, policy, b["hops"][: pos - 1] + [bad], pos + 1, b["notes"][:pos])
            reuse = [h["checks"] for h in b["trace"]["hops"]]
            trace = run_checks(checker, case.transcript, hops, final, pos, reuse, notes)
            took = True
        log.info("%-9s %-40s pos=%d  %s", level, case.case_id, pos, fault)
        return {**head, "applied": True, "fault": fault, "final": final, "trace": trace, "case": case, "took": took}

    jobs = [(b, lv, ps) for b in base for lv in HANDOFF_LEVELS for ps in positions]
    jobs += [(b, "confirmed", 0) for b in base]
    fault_runs = parallel_map(faulted, jobs, a.workers)
    if over_budget(models, a.max_failures):
        raise SystemExit(f"STOPPED after {sum(m.failures for m in models)} failed API calls; fix the cause and rerun.")

    rows, traces = [], []
    for b in base:
        case, final = b["case"], b["trace"]["final"]["action"]
        ok = same_action(final, case.correct_action)
        natural = next((i + 1 for i, h in enumerate(b["hops"]) if not carries_correct_change(h, case)), None)
        row = {
            "case_id": case.case_id,
            "level": "clean",
            "position": "",
            "applied": True,
            "fault": "",
            "final_correct": ok,
            "reached_end": not ok and final.get("name") in WRITE_TOOLS,
            "natural_error_hop": natural if not ok else "",
        }
        rows.append(_score_row(row, b["trace"]))
        traces.append({"case_id": case.case_id, "level": "clean", "position": "", **b["trace"]})
    for r in fault_runs:
        if not r["applied"]:
            rows.append({k: r[k] for k in ("case_id", "level", "position", "applied", "fault")})
            continue
        case, final, trace = r["case"], r["final"], r["trace"]
        allowed = trace["hops"][N_HOPS - 1]["handoff"].get("policy_allowed") is not False
        wrong = not same_action(final, case.correct_action)
        row = {
            "case_id": r["case_id"],
            "level": r["level"],
            "position": r["position"],
            "applied": True,
            "fault": r["fault"],
            "took": r["took"],
            "expected_where": r["position"] or 1,
            "final_correct": not wrong,
            "reached_end": allowed and final.get("name") in WRITE_TOOLS and wrong,
        }
        rows.append(_score_row(row, trace))
        traces.append(
            {"case_id": r["case_id"], "level": r["level"], "position": r["position"], "fault": r["fault"], **trace}
        )

    write_csv(out / "lab_results.csv", rows)
    write_jsonl(out / "lab_traces.jsonl", traces)
    log.info("%d model calls. Wrote %s. Summarise with: blindspots analyze", agent.calls + checker.calls, out)
