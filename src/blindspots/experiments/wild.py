"""Experiment 2 ("in the wild"): does the same checker catch mistakes agents really made?

No planted faults and no hand labels. Labels come from two independent sources that must agree:
  1. Outcome filter (code): a write call that wasn't an expected change, in a conversation that failed, is a
     mistake candidate; an expected change in a conversation that passed is a correct candidate.
  2. Adjudicator (a different model family from the checker): sees the customer's SECRET GOAL, which the agent and
     the checker never see, and rules "mistake", "acceptable" or "unclear".
Only cases where both agree are kept. The checker then sees what a production checker would see: the conversation
("full") or only the records ("records"), plus the proposed action.

Writes <out>/wild_results.csv. Interrupted runs resume from <out>/wild_results.csv.progress.jsonl.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from blindspots import prompts
from blindspots.llm import LLM, PROVIDERS
from blindspots.runner import ProgressLog, over_budget, parallel_map, preflight, write_csv
from blindspots.tau2 import DEFAULT_TAU2_DIR, RealAction, action_key, records_only, sample_real_actions

log = logging.getLogger(__name__)
VERDICTS = ("mistake", "acceptable", "unclear")
COLUMNS = [
    "case_id",
    "candidate",
    "adjudicator",
    "kept",
    "full_flag",
    "records_flag",
    "adjudicator_reason",
    "full_explanation",
    "action",
]


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tau2-dir", type=Path, default=DEFAULT_TAU2_DIR)
    p.add_argument("--n", type=int, default=120, help="candidates to draw of each kind (some get dropped)")
    p.add_argument("--provider", default="anthropic", choices=PROVIDERS)
    p.add_argument("--checker-model", default="claude-haiku-5-5")
    p.add_argument("--adjudicator-provider", default="openai", choices=PROVIDERS)
    p.add_argument(
        "--adjudicator-model",
        default="gpt-6.2-sol",
        help="a strong model, ideally from a different family than the checker",
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=8, help="parallel API calls; lower it if you hit rate limits")
    p.add_argument("--max-failures", type=int, default=5, help="stop after this many failed API calls")
    p.add_argument("--out", type=Path, default=Path("results/wild"))
    p.add_argument("--dry-run", action="store_true", help="stub replies, no API calls")


def adjudicate(judge: LLM, it: RealAction, stub_verdict: str) -> dict[str, Any]:
    return judge.ask_json(
        prompts.ADJUDICATE,
        f"CUSTOMER'S SECRET GOAL:\n{json.dumps(it.goal)}\n\n"
        f"CONVERSATION:\n{it.transcript}\n\nACTION:\n{json.dumps(it.action)}",
        stub={"verdict": stub_verdict, "reason": ""},
    ).data


def check_full(checker: LLM, it: RealAction, prompt: str = prompts.CHECK, stub_ok: bool = True) -> dict[str, Any]:
    """The checker as deployed: the conversation plus the proposed action. No secret goal."""
    return checker.ask_json(
        prompt, f"CONVERSATION:\n{it.transcript}\n\nACTION TO CHECK:\n{json.dumps(it.action)}", stub={"ok": stub_ok}
    ).data


def check_records(checker: LLM, it: RealAction) -> dict[str, Any]:
    """The checker without the conversation: only the records the agent looked up."""
    return checker.ask_json(
        prompts.CHECK,
        f"RECORDS THE AGENT LOOKED UP:\n{records_only(it.transcript)}\n\nACTION TO CHECK:\n{json.dumps(it.action)}",
        stub={"ok": True},
    ).data


def run(a: argparse.Namespace) -> None:
    out = Path("results/dry-run/wild") if a.dry_run else a.out
    out.mkdir(parents=True, exist_ok=True)
    mistakes, correct, n_mistakes, n_correct = sample_real_actions(a.tau2_dir, a.n, a.seed)
    checker = LLM(a.provider, a.checker_model, a.dry_run)
    judge = LLM(a.adjudicator_provider, a.adjudicator_model, a.dry_run)
    log.info(
        "pool: %d mistake / %d correct candidates | drawing %d + %d | checker %s | adjudicator %s",
        n_mistakes,
        n_correct,
        len(mistakes),
        len(correct),
        checker,
        judge,
    )

    probe = (mistakes or correct)[0]
    preflight(
        {
            "adjudicator": (adjudicate(judge, probe, "mistake"), lambda r: r.get("verdict") in VERDICTS),
            "checker": (check_full(checker, probe), lambda r: "ok" in r),
        }
    )

    progress = ProgressLog(
        out / "wild_results.csv.progress.jsonl", key=lambda row: action_key(row["case_id"], json.loads(row["action"]))
    )

    def label_and_check(job: tuple[str, RealAction]) -> dict[str, Any] | None:
        candidate, it = job
        if (row := progress.get(it.key)) is not None:
            return row
        if over_budget((checker, judge), a.max_failures):
            return None
        verdict = adjudicate(judge, it, "mistake" if candidate == "mistake" else "acceptable")
        v = verdict.get("verdict")
        if v is None:
            return None  # the call failed: not saved, so a rerun retries it
        keep = (candidate, v) in {("mistake", "mistake"), ("correct", "acceptable")}
        row = {
            "case_id": it.case_id,
            "candidate": candidate,
            "adjudicator": v,
            "kept": keep,
            "adjudicator_reason": verdict.get("reason", ""),
            "action": json.dumps(it.action),
        }
        if keep:  # checkers only run on agreed labels
            full, rec = check_full(checker, it), check_records(checker, it)
            row.update(
                full_flag=full.get("ok") is False,
                records_flag=rec.get("ok") is False,
                full_explanation=full.get("explanation", ""),
            )
        progress.append(row)
        log.info(
            "%-8s adjudicator=%-10s kept=%-5s full=%-5s  %s", candidate, v, keep, row.get("full_flag", "-"), it.case_id
        )
        return row

    jobs = [("mistake", it) for it in mistakes] + [("correct", it) for it in correct]
    rows = parallel_map(label_and_check, jobs, a.workers)
    if over_budget((checker, judge), a.max_failures):
        raise SystemExit(f"STOPPED after repeated API failures. {len(rows)} cases are saved; rerun to continue.")
    write_csv(out / "wild_results.csv", rows, COLUMNS)
    log.info("%d model calls. Wrote %s. Summarise with: blindspots analyze", checker.calls + judge.calls, out)
