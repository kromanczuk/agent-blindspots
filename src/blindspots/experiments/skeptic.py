"""Experiment 2b: can a better prompt close the planted-vs-real gap?

Reuses the agreed labels from Experiment 2 (nothing is labelled again). For every kept case:
  baseline  the original checker prompt, run again (this also measures run-to-run noise)
  skeptic   same model, same inputs, but a prompt that does NOT treat the customer's "yes" as proof
For every kept real mistake, a judge also answers one question:
  clue      could a reviewer who sees only the conversation have known the action was wrong?
            This splits mistakes into ones a chat-only checker could catch and ones it never could.

Writes <out>/skeptic_results.csv. Interrupted runs resume from <out>/skeptic_results.csv.progress.jsonl.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

from blindspots import prompts
from blindspots.experiments.wild import check_full
from blindspots.llm import LLM, PROVIDERS
from blindspots.runner import ProgressLog, over_budget, parallel_map, preflight, write_csv
from blindspots.tau2 import DEFAULT_TAU2_DIR, RealAction, action_key, real_action_pool

log = logging.getLogger(__name__)


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tau2-dir", type=Path, default=DEFAULT_TAU2_DIR)
    p.add_argument(
        "--labels",
        type=Path,
        default=Path("results/wild/wild_results.csv"),
        help="the CSV written by `blindspots wild`",
    )
    p.add_argument("--provider", default="anthropic", choices=PROVIDERS)
    p.add_argument("--checker-model", default="claude-haiku-5-5")
    p.add_argument("--judge-provider", default="openai", choices=PROVIDERS)
    p.add_argument("--judge-model", default="gpt-6.2-sol", help="ideally the same model as the adjudicator")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-failures", type=int, default=5)
    p.add_argument("--out", type=Path, default=Path("results/skeptic"))
    p.add_argument("--dry-run", action="store_true", help="stub replies, no API calls")


def ask_clue(judge: LLM, it: RealAction, why_wrong: str) -> dict[str, Any]:
    return judge.ask_json(
        prompts.CLUE,
        f"CONVERSATION:\n{it.transcript}\n\nACTION:\n{json.dumps(it.action)}\n\nWHY IT WAS WRONG:\n{why_wrong}",
        stub={"clue": "yes", "evidence": ""},
    ).data


def load_labelled(labels: Path, tau2_dir: Path) -> list[tuple[dict[str, str], RealAction]]:
    """Pair every kept label with its recorded action, matching on case_id AND the exact call.

    One message can hold several write calls (GPT agents call tools in parallel), so case_id alone is ambiguous.
    """
    kept = [r for r in csv.DictReader(labels.open()) if r.get("kept") == "True"]
    if not kept:
        raise SystemExit(f"No kept cases in {labels}. Run `blindspots wild` first.")
    mistakes, correct = real_action_pool(tau2_dir)
    by_key = {it.key: it for it in mistakes + correct}
    pairs = [(r, by_key[k]) for r in kept if (k := action_key(r["case_id"], json.loads(r["action"]))) in by_key]
    if len(pairs) < len(kept):
        log.warning("%d labelled cases were not found in %s and are skipped", len(kept) - len(pairs), tau2_dir)
    return pairs


def run(a: argparse.Namespace) -> None:
    out = Path("results/dry-run/skeptic") if a.dry_run else a.out
    out.mkdir(parents=True, exist_ok=True)
    cases = load_labelled(a.labels, a.tau2_dir)
    n_m = sum(lab["candidate"] == "mistake" for lab, _ in cases)
    checker = LLM(a.provider, a.checker_model, a.dry_run)
    judge = LLM(a.judge_provider, a.judge_model, a.dry_run)
    log.info(
        "%d labelled cases: %d mistakes, %d correct | about %d calls",
        len(cases),
        n_m,
        len(cases) - n_m,
        2 * len(cases) + n_m,
    )

    probe_lab, probe = next((c for c in cases if c[0]["candidate"] == "mistake"), cases[0])
    preflight(
        {
            "skeptic": (check_full(checker, probe, prompts.SKEPTIC, False), lambda r: "ok" in r),
            "clue": (ask_clue(judge, probe, probe_lab["adjudicator_reason"]), lambda r: r.get("clue") in ("yes", "no")),
        }
    )

    progress = ProgressLog(
        out / "skeptic_results.csv.progress.jsonl",
        key=lambda row: action_key(row["case_id"], json.loads(row["action"])),
    )

    def recheck(case: tuple[dict[str, str], RealAction]) -> dict[str, Any] | None:
        lab, it = case
        if (row := progress.get(it.key)) is not None:
            return row
        if over_budget((checker, judge), a.max_failures):
            return None
        base = check_full(checker, it, prompts.CHECK, True)
        skep = check_full(checker, it, prompts.SKEPTIC, lab["candidate"] == "correct")
        if "ok" not in base or "ok" not in skep:
            return None  # a failed call: not saved, so a rerun retries it
        row = {
            "case_id": it.case_id,
            "candidate": lab["candidate"],
            "original_flag": lab.get("full_flag") == "True",
            "baseline_flag": base["ok"] is False,
            "skeptic_flag": skep["ok"] is False,
            "clue": "",
            "clue_evidence": "",
            "baseline_explanation": base.get("explanation", ""),
            "skeptic_explanation": skep.get("explanation", ""),
            "adjudicator_reason": lab.get("adjudicator_reason", ""),
            "action": json.dumps(it.action),
        }
        if lab["candidate"] == "mistake":
            c = ask_clue(judge, it, lab["adjudicator_reason"])
            if c.get("clue") not in ("yes", "no"):
                return None
            row.update(clue=c["clue"], clue_evidence=c.get("evidence", ""))
        progress.append(row)
        log.info(
            "%-8s baseline=%-5s skeptic=%-5s clue=%-3s  %s",
            row["candidate"],
            row["baseline_flag"],
            row["skeptic_flag"],
            row["clue"] or "-",
            it.case_id,
        )
        return row

    rows = parallel_map(recheck, cases, a.workers)
    if over_budget((checker, judge), a.max_failures):
        raise SystemExit(f"STOPPED after repeated API failures. {len(rows)} cases are saved; rerun to continue.")
    write_csv(out / "skeptic_results.csv", rows)
    log.info("%d model calls. Wrote %s. Summarise with: blindspots analyze", checker.calls + judge.calls, out)
