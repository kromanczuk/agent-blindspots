"""Recompute every reported number from the saved results. Needs no API keys and no benchmark download.

    blindspots analyze                      # prints the report, writes results/summary.json

All three experiments are summarised from their CSV/JSONL files in `results/`. Guards in Experiment 1 are scored
only on runs where a wrong change actually reached the final action: if the agents themselves stopped the run,
there was nothing left for a guard to catch.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from blindspots.faults import HANDOFF_LEVELS, planted_field
from blindspots.guards import CONFIGS, first_flag, score
from blindspots.stats import Rate, mcnemar_exact, rate

RESULTS = Path("results")
PRICE_IN, PRICE_OUT = 0.10, 0.50  # $ per million tokens, Claude Haiku 5.5 list price
POSITIONS = (1, 2, 4)

# Keyword rules for the explanation analysis. Deliberately simple and approximate (see docs/METHODS.md).
CITES_REQUEST = re.compile(r"request|asked|wants|wanted", re.I)
CITES_CONFIRMATION = re.compile(r"confirm", re.I)


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--results", type=Path, default=RESULTS)
    p.add_argument("--out", type=Path, default=RESULTS / "summary.json")


def _bool(v: Any) -> bool:
    return v is True or v == "True"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _r(r: Rate) -> dict[str, float]:
    return r.to_dict()


# ------------------------------------------------------------------------------------------ Experiment 1: lab


def load_lab(results: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Rows for every run, and the trace of every applied run, aligned row-for-row.

    The saved traces carry no `position` field, but they were written in the same order as the applied rows,
    so they are matched by order and checked on case_id and level.
    """
    rows = read_csv(results / "lab" / "lab_results.csv")
    applied = [r for r in rows if _bool(r["applied"])]
    traces = [json.loads(line) for line in (results / "lab" / "lab_traces.jsonl").read_text().splitlines()]
    if len(applied) != len(traces):
        raise ValueError(f"{len(applied)} applied runs but {len(traces)} traces")
    for row, tr in zip(applied, traces, strict=True):
        if (row["case_id"], row["level"]) != (tr["case_id"], tr["level"]):
            raise ValueError(f"trace order mismatch at {row['case_id']} {row['level']}")
        tr["position"] = int(row["position"] or 0)
    return rows, traces


def _only_policy_field(verdict: dict[str, Any]) -> bool:
    """A failed check that only disputes `policy_allowed`, an internal field the conversation can't confirm."""
    fields = verdict.get("wrong_fields") or []
    return bool(fields) and all(f == "policy_allowed" for f in fields)


def _names_planted_field(verdict: dict[str, Any], field: str | None) -> bool:
    stem = (field or "").split("_")[0]
    return bool(stem) and any(stem in str(f).lower() for f in verdict.get("wrong_fields") or [])


def summarize_lab(rows: list[dict[str, str]], traces: list[dict[str, Any]]) -> dict[str, Any]:
    runs = [(r, t) for r, t in zip([r for r in rows if _bool(r["applied"])], traces, strict=True)]
    clean = [(r, t) for r, t in runs if r["level"] == "clean"]
    good = [(r, t) for r, t in clean if _bool(r["final_correct"])]
    handoff = [(r, t) for r, t in runs if r["level"] in HANDOFF_LEVELS]
    confirmed = [(r, t) for r, t in runs if r["level"] == "confirmed"]
    faults = [(r, t) for r, t in handoff if _bool(r["reached_end"])]
    conf = [(r, t) for r, t in confirmed if _bool(r["reached_end"])]

    configs = {}
    for c in CONFIGS:
        caught = [(r, t) for r, t in faults + conf if _bool(r[f"{c}_flag"])]
        avg = {
            k: sum(float(r[f"{c}_{k}"] or 0) for r, _ in clean) / len(clean)
            for k in ("tokens_in", "tokens_out", "seconds")
        }
        first = [(first_flag(t, c), t) for _, t in caught]
        configs[c] = {
            "llm_calls": int(clean[0][0][f"{c}_calls"]),
            "caught": _r(rate(_bool(r[f"{c}_flag"]) for r, _ in faults)),
            "confirmed_caught": _r(rate(_bool(r[f"{c}_flag"]) for r, _ in conf)),
            "false_alarms": _r(rate(_bool(r[f"{c}_flag"]) for r, _ in good)),
            "false_alarms_adjusted": _r(rate(score(t, c, ignore=_only_policy_field)[0] for _, t in good)),
            "right_step": _r(rate(r[f"{c}_where"] == r["expected_where"] for r, _ in caught))
            if CONFIGS[c]["every_hop"]
            else None,
            "right_reason": _r(rate(_names_planted_field(f[2], planted_field(t.get("fault", ""))) for f, t in first)),
            "cost_per_1000_runs": round(1000 * (avg["tokens_in"] * PRICE_IN + avg["tokens_out"] * PRICE_OUT) / 1e6, 2),
            "delay_seconds": round(avg["seconds"], 1),
            "tokens_in": round(avg["tokens_in"]),
            "tokens_out": round(avg["tokens_out"]),
            "by_position": {
                str(p): _r(rate(_bool(r[f"{c}_flag"]) for r, _ in faults if r["position"] == str(p))) for p in POSITIONS
            },
            "by_level": {
                lv: _r(rate(_bool(r[f"{c}_flag"]) for r, _ in faults if r["level"] == lv)) for lv in HANDOFF_LEVELS
            },
        }

    skipped = Counter(r["level"] for r in rows if not _bool(r["applied"]))
    return {
        "cases": len(clean),
        "clean": {
            "correct": len(good),
            "wrong_change_written": sum(_bool(r["reached_end"]) for r, _ in clean),
            "stopped_by_agents": len(clean) - len(good) - sum(_bool(r["reached_end"]) for r, _ in clean),
        },
        "handoff_faults": {
            "applied": len(handoff),
            "reached_end": len(faults),
            "stopped_by_agents": len(handoff) - len(faults),
            "skipped_not_applicable": sum(skipped[lv] for lv in HANDOFF_LEVELS),
            "by_level": {
                lv: {
                    "applied": sum(r["level"] == lv for r, _ in handoff),
                    "reached_end": sum(r["level"] == lv for r, _ in faults),
                }
                for lv in HANDOFF_LEVELS
            },
            "by_position": {
                str(p): {
                    "applied": sum(r["position"] == str(p) for r, _ in handoff),
                    "reached_end": sum(r["position"] == str(p) for r, _ in faults),
                }
                for p in POSITIONS
            },
        },
        "confirmed_faults": {
            "planted": len(confirmed),
            "took_hold": sum(_bool(r.get("took")) for r, _ in confirmed),
            "reached_end": len(conf),
        },
        "configs": configs,
    }


# ----------------------------------------------------------------------------------------- Experiment 2: wild


def summarize_wild(rows: list[dict[str, str]]) -> dict[str, Any]:
    kept = [r for r in rows if _bool(r["kept"])]
    mistakes = [r for r in kept if r["candidate"] == "mistake"]
    correct = [r for r in kept if r["candidate"] == "correct"]
    missed = [r for r in mistakes if not _bool(r["full_flag"])]
    caught = [r for r in mistakes if _bool(r["full_flag"])]

    def by(key) -> dict[str, dict[str, float]]:
        groups: dict[str, list[dict[str, str]]] = {}
        for r in mistakes:
            groups.setdefault(key(r), []).append(r)
        return {g: _r(rate(_bool(r["full_flag"]) for r in rs)) for g, rs in sorted(groups.items())}

    return {
        "candidates": Counter(r["candidate"] for r in rows),
        "labels": {f"{c}->{a}": n for (c, a), n in Counter((r["candidate"], r["adjudicator"]) for r in rows).items()},
        "kept": {"mistakes": len(mistakes), "correct": len(correct)},
        "filter_overturned": _r(rate(r["adjudicator"] != "mistake" for r in rows if r["candidate"] == "mistake")),
        "full": {
            "caught": _r(rate(_bool(r["full_flag"]) for r in mistakes)),
            "false_alarms": _r(rate(_bool(r["full_flag"]) for r in correct)),
        },
        "records": {
            "caught": _r(rate(_bool(r["records_flag"]) for r in mistakes)),
            "false_alarms": _r(rate(_bool(r["records_flag"]) for r in correct)),
        },
        "caught_by_action": by(lambda r: json.loads(r["action"])["name"]),
        "caught_by_agent": by(lambda r: r["case_id"].split("_")[1]),
        "explanations": {
            "missed": len(missed),
            "missed_cites_request": sum(bool(CITES_REQUEST.search(r["full_explanation"])) for r in missed),
            "missed_cites_confirmation": sum(bool(CITES_CONFIRMATION.search(r["full_explanation"])) for r in missed),
            "caught": len(caught),
            "caught_cites_confirmation": sum(bool(CITES_CONFIRMATION.search(r["full_explanation"])) for r in caught),
        },
    }


# ------------------------------------------------------------------------------------- Experiment 2b: skeptic


def pair_skeptic(labels: list[dict[str, str]], rows: list[dict[str, str]]) -> list[tuple[dict, dict]]:
    """Pair each skeptic row with the label it was run for, and drop rows checked against the wrong action.

    The skeptic run that produced these results matched labels on case_id alone. Where one message held two write
    calls, the checker saw the other call. Rows were written in label order (one label failed and is absent), so
    walking both lists in order recovers the pairing; rows whose action differs from their label's are dropped.
    """
    kept = [r for r in labels if _bool(r["kept"])]
    pairs, i = [], 0
    for row in rows:
        while kept[i]["case_id"] != row["case_id"]:
            i += 1
        pairs.append((kept[i], row))
        i += 1

    def same(a: str, b: str) -> bool:
        return json.loads(a) == json.loads(b)

    return [(lab, row) for lab, row in pairs if same(lab["action"], row["action"])]


def summarize_skeptic(labels: list[dict[str, str]], rows: list[dict[str, str]]) -> dict[str, Any]:
    pairs = pair_skeptic(labels, rows)
    usable = [row for _, row in pairs]
    m = [r for r in usable if r["candidate"] == "mistake"]
    c = [r for r in usable if r["candidate"] == "correct"]
    clue, no_clue = [r for r in m if r["clue"] == "yes"], [r for r in m if r["clue"] == "no"]
    runs = ("original", "baseline", "skeptic")
    return {
        "rows": len(rows),
        "usable": len(usable),
        "dropped_wrong_action": len(rows) - len(usable),
        "mistakes": len(m),
        "correct": len(c),
        "caught": {k: _r(rate(_bool(r[f"{k}_flag"]) for r in m)) for k in runs},
        "false_alarms": {k: _r(rate(_bool(r[f"{k}_flag"]) for r in c)) for k in runs},
        "skeptic_vs_baseline": {
            "mistakes": mcnemar_exact([_bool(r["skeptic_flag"]) for r in m], [_bool(r["baseline_flag"]) for r in m]),
            "correct": mcnemar_exact([_bool(r["skeptic_flag"]) for r in c], [_bool(r["baseline_flag"]) for r in c]),
        },
        "run_to_run_flips": sum(_bool(r["original_flag"]) != _bool(r["baseline_flag"]) for r in usable),
        "clue_in_chat": _r(rate(r["clue"] == "yes" for r in m)),
        "caught_with_clue": {k: _r(rate(_bool(r[f"{k}_flag"]) for r in clue)) for k in runs},
        "caught_without_clue": {k: _r(rate(_bool(r[f"{k}_flag"]) for r in no_clue)) for k in runs},
    }


# -------------------------------------------------------------------------------------------------- report


def summarize(results: Path = RESULTS) -> dict[str, Any]:
    rows, traces = load_lab(results)
    wild_rows = read_csv(results / "wild" / "wild_results.csv")
    skeptic_rows = read_csv(results / "skeptic" / "skeptic_results.csv")
    lab = summarize_lab(rows, traces)
    wild = summarize_wild(wild_rows)
    return {
        "headline": {"planted_caught": lab["configs"]["end_only"]["caught"], "real_caught": wild["full"]["caught"]},
        "lab": lab,
        "wild": wild,
        "skeptic": summarize_skeptic(wild_rows, skeptic_rows),
    }


def _fmt(d: dict[str, float] | None) -> str:
    if not d:
        return "n/a"
    return str(Rate(int(d["k"]), int(d["n"])))


def report(s: dict[str, Any]) -> str:
    lab, wild, sk = s["lab"], s["wild"], s["skeptic"]
    hf, cf = lab["handoff_faults"], lab["confirmed_faults"]
    out = [
        "HEADLINE",
        f"  planted mistakes caught (one AI check at the end): {_fmt(s['headline']['planted_caught'])}",
        f"  real mistakes caught (same checker, full chat):    {_fmt(s['headline']['real_caught'])}",
        "",
        f"EXPERIMENT 1 - in the lab ({lab['cases']} cases)",
        f"  clean runs: {lab['clean']['correct']} correct, {lab['clean']['stopped_by_agents']} stopped by the agents",
        f"  hand-off faults: {hf['applied']} applied, {hf['reached_end']} reached the final action",
        f"  confirmed faults: {cf['planted']} planted, {cf['took_hold']} took hold, "
        f"{cf['reached_end']} reached the end",
        "",
        f"  {'config':12}{'caught':>25}{'confirmed':>23}{'false alarms':>22}{'adjusted':>22}"
        f"{'right step':>25}{'$/1000':>8}{'delay':>7}",
    ]
    for c, v in lab["configs"].items():
        out.append(
            f"  {c:12}{_fmt(v['caught']):>25}{_fmt(v['confirmed_caught']):>23}{_fmt(v['false_alarms']):>22}"
            f"{_fmt(v['false_alarms_adjusted']):>22}{_fmt(v['right_step']):>25}"
            f"{v['cost_per_1000_runs']:>8.2f}{v['delay_seconds']:>6.1f}s"
        )
    out += ["", "  caught by where the fault entered (no_source vs end_only):"]
    for c in ("no_source", "end_only"):
        cells = "  ".join(f"hop {p}: {_fmt(r)}" for p, r in lab["configs"][c]["by_position"].items())
        out.append(f"    {c:12}{cells}")
    out += ["", "  right reason (first flag names the planted field):"]
    for c in ("end_only", "every_step", "lightweight", "no_source"):
        out.append(f"    {c:12}{_fmt(lab['configs'][c]['right_reason'])}")
    ex = wild["explanations"]
    out += [
        "",
        f"EXPERIMENT 2 - in the wild ({wild['kept']['mistakes']} real mistakes, {wild['kept']['correct']} correct)",
        f"  outcome filter overturned by the adjudicator: {_fmt(wild['filter_overturned'])}",
        f"  full chat:     caught {_fmt(wild['full']['caught'])}   false alarms {_fmt(wild['full']['false_alarms'])}",
        f"  records only:  caught {_fmt(wild['records']['caught'])}   "
        f"false alarms {_fmt(wild['records']['false_alarms'])}",
        f"  missed mistakes whose explanation cites the customer's request: "
        f"{ex['missed_cites_request']}/{ex['missed']}, "
        f"cites a confirmation: {ex['missed_cites_confirmation']}/{ex['missed']}",
        "",
        f"EXPERIMENT 2b - a skeptical prompt ({sk['usable']} usable cases: {sk['mistakes']} mistakes, "
        f"{sk['correct']} correct; {sk['dropped_wrong_action']} dropped)",
    ]
    for k in ("original", "baseline", "skeptic"):
        out.append(f"  {k:9} caught {_fmt(sk['caught'][k]):>20}   false alarms {_fmt(sk['false_alarms'][k]):>20}")
    mc = sk["skeptic_vs_baseline"]
    out += [
        f"  skeptic vs baseline (exact McNemar): mistakes p={mc['mistakes']['p_value']}, "
        f"correct p={mc['correct']['p_value']}",
        f"  run-to-run: {sk['run_to_run_flips']} of {sk['usable']} verdicts changed between identical runs",
        f"  clue in the chat: {_fmt(sk['clue_in_chat'])}",
        f"  original checker caught: with clue {_fmt(sk['caught_with_clue']['original'])}, "
        f"without {_fmt(sk['caught_without_clue']['original'])}",
    ]
    return "\n".join(out)


def run(a: argparse.Namespace) -> None:
    s = summarize(a.results)
    print(report(s))
    a.out.write_text(json.dumps(s, indent=2, allow_nan=False) + "\n")
    print(f"\nwrote {a.out}")
