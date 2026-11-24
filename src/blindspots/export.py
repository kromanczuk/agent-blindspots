"""Export the data the web explorer reads to site/public/data/.

    blindspots export-site

Writes
  summary.json   every number in the report (same as results/summary.json)
  cases.json     every labelled real action from Experiment 2: the conversation up to the action, the customer's
                 secret goal, the labels, every checker verdict and explanation, and the clue judgement
  lab.json       the worked Experiment 1 example: one case's clean run and a planted fault, hop by hop

The output is self-contained, so the site needs neither the benchmark download nor any API key.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from blindspots import analysis
from blindspots.tau2 import DEFAULT_TAU2_DIR, agent_model, build_lab_cases, recording_files

SITE_DATA = Path("site/public/data")
FIGURE = Path("docs/figures/headline.svg")
LAB_EXAMPLE = {"case_id": "task26_claude-3-7-sonnet-20250219", "fault": ("medium", 1)}
FEATURED = "task79_claude-3-7-sonnet-20250219_t1_m"  # Emma's water bottle, shown first on the site


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tau2-dir", type=Path, default=DEFAULT_TAU2_DIR)
    p.add_argument("--results", type=Path, default=analysis.RESULTS)
    p.add_argument("--out", type=Path, default=SITE_DATA)


def _messages(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only what a reader needs: who spoke, what they said, and which tools the agent called."""
    out = []
    for m in msgs:
        item: dict[str, Any] = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("tool_calls"):
            item["tool_calls"] = [{"name": tc["name"], "arguments": tc["arguments"]} for tc in m["tool_calls"]]
        out.append(item)
    return out


def _load_recordings(tau2_dir: Path) -> tuple[dict[tuple[str, str, int], list], dict[str, Any]]:
    """(model, task_id, trial) -> messages, and task_id -> the customer's secret instructions."""
    sims, goals = {}, {}
    for path in recording_files(tau2_dir):
        model = agent_model(path)
        data = json.loads(path.read_text())
        for t in data.get("tasks", []):
            goals[str(t["id"])] = (t.get("user_scenario") or {}).get("instructions")
        for s in data["simulations"]:
            sims[(model, str(s["task_id"]), int(s["trial"]))] = s["messages"]
    return sims, goals


def _parse_case_id(case_id: str) -> tuple[str, str, int, int]:
    """'task79_claude-3-7-sonnet-20250219_t1_m25' -> ('claude-3-7-sonnet-20250219', '79', 1, 25)."""
    task, rest = case_id.split("_", 1)
    model, trial, msg = rest.rsplit("_", 2)
    return model, task.removeprefix("task"), int(trial[1:]), int(msg[1:])


def export_cases(results: Path, tau2_dir: Path) -> list[dict[str, Any]]:
    wild_rows = analysis.read_csv(results / "wild" / "wild_results.csv")
    skeptic_rows = analysis.read_csv(results / "skeptic" / "skeptic_results.csv")
    second = {(lab["case_id"], lab["action"]): row for lab, row in analysis.pair_skeptic(wild_rows, skeptic_rows)}
    sims, goals = _load_recordings(tau2_dir)

    cases = []
    for r in wild_rows:
        if r["kept"] != "True":
            continue
        model, task, trial, msg = _parse_case_id(r["case_id"])
        sk = second.get((r["case_id"], r["action"]))
        cases.append(
            {
                "id": f"{r['case_id']}:{len(cases)}",
                "case_id": r["case_id"],
                "task": task,
                "agent": model,
                "trial": trial,
                "label": r["candidate"],  # "mistake" or "correct": filter and adjudicator agreed
                "action": json.loads(r["action"]),
                "adjudicator_reason": r["adjudicator_reason"],
                "checker": {"flagged": r["full_flag"] == "True", "explanation": r["full_explanation"]},
                "records_checker_flagged": r["records_flag"] == "True",
                "rerun": None
                if sk is None
                else {
                    "baseline_flagged": sk["baseline_flag"] == "True",
                    "baseline_explanation": sk["baseline_explanation"],
                    "skeptic_flagged": sk["skeptic_flag"] == "True",
                    "skeptic_explanation": sk["skeptic_explanation"],
                    "clue": sk["clue"] or None,
                    "clue_evidence": sk["clue_evidence"] or None,
                },
                "goal": goals.get(task),
                "messages": _messages(sims[(model, task, trial)][:msg]),
                "featured": r["case_id"].startswith(FEATURED),
            }
        )
    return cases


def export_lab_example(results: Path, tau2_dir: Path) -> dict[str, Any]:
    case = next(c for c in build_lab_cases(tau2_dir, 10**6) if c.case_id == LAB_EXAMPLE["case_id"])
    level, pos = LAB_EXAMPLE["fault"]
    _, traces = analysis.load_lab(results)
    runs = {}
    for t in traces:
        if t["case_id"] != case.case_id:
            continue
        if t["level"] == "clean":
            runs["clean"] = t
        elif (t["level"], t["position"]) == (level, pos):
            runs["fault"] = t
    model, task = case.case_id.split("_", 1)[1], case.case_id.split("_")[0].removeprefix("task")
    sims, _ = _load_recordings(tau2_dir)
    messages = sims[(model, task, case.trial)][: case.cut]
    return {
        "case_id": case.case_id,
        "correct_action": case.correct_action,
        "messages": _messages(messages),
        "runs": runs,
    }


def headline_svg(summary: dict[str, Any]) -> str:
    """The README figure: the same checker on planted vs. real mistakes, with 95% intervals."""
    rows = [
        ("Planted mistakes", "end check, full chat", summary["headline"]["planted_caught"], "#00539b"),
        ("Real mistakes", "same check, full chat", summary["wild"]["full"]["caught"], "#c84e00"),
        ("Real mistakes", "records only, no chat", summary["wild"]["records"]["caught"], "#7a7c85"),
    ]
    x0, width, top, step = 230, 420, 64, 52
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="250" viewBox="0 0 760 250" '
        'font-family="system-ui,-apple-system,Segoe UI,Roboto,sans-serif">',
        '<rect width="760" height="250" rx="12" fill="#fbf9f4"/>',
        '<text x="24" y="34" font-size="17" font-weight="650" fill="#141a2e">'
        "Share of mistakes the checker flagged (Claude Haiku 5.5)</text>",
    ]
    for i, (label, sub, r, color) in enumerate(rows):
        y = top + i * step
        frac = r["k"] / r["n"]
        parts += [
            f'<text x="24" y="{y + 12}" font-size="14" font-weight="600" fill="#141a2e">{label}</text>',
            f'<text x="24" y="{y + 30}" font-size="12" fill="#7a7c85">{sub} · {r["k"]}/{r["n"]}</text>',
            f'<rect x="{x0}" y="{y + 6}" width="{width}" height="14" rx="7" fill="#e8e5df"/>',
            f'<rect x="{x0}" y="{y + 6}" width="{width * frac:.1f}" height="14" rx="7" fill="{color}"/>',
            f'<rect x="{x0 + width * r["lo"] / 100:.1f}" y="{y + 12}" width="{width * (r["hi"] - r["lo"]) / 100:.1f}" '
            'height="2" fill="#141a2e" opacity="0.35"/>',
            f'<text x="{x0 + width + 14}" y="{y + 18}" font-size="15" font-weight="650" fill="#141a2e">'
            f"{round(100 * frac)}%</text>",
        ]
    parts.append('<text x="24" y="234" font-size="11.5" fill="#7a7c85">Thin lines: Wilson 95% intervals.</text>')
    return "\n".join([*parts, "</svg>"]) + "\n"


def run(a: argparse.Namespace) -> None:
    a.out.mkdir(parents=True, exist_ok=True)
    summary = analysis.summarize(a.results)
    cases = export_cases(a.results, a.tau2_dir)
    lab = export_lab_example(a.results, a.tau2_dir)
    for name, data in (("summary", summary), ("cases", cases), ("lab", lab)):
        path = a.out / f"{name}.json"
        path.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))
        print(f"wrote {path} ({path.stat().st_size / 1e6:.2f} MB)")
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    FIGURE.write_text(headline_svg(summary))
    print(f"wrote {FIGURE}")
