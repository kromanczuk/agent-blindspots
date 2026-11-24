"""Guards: checks that run on a hand-off between agents, or on the final action before it executes.

Three kinds of check:
  code    free: every ID in the hand-off must appear somewhere in the conversation
  source  one LLM call: does the hand-off match the ORIGINAL conversation?
  local   one LLM call: does it match the records alone (no conversation)? This is what a checker sees in a
          pipeline that doesn't carry the source along.

A guard CONFIG says which kinds run at every hop and which at the end. Experiment 1 runs every kind at every
checkpoint once and logs the verdicts (the trace); `score` then applies each config to the same trace, so all
configs are compared on exactly the same runs and the comparison needs only one experiment run.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from blindspots.llm import LLM
from blindspots.prompts import CHECK
from blindspots.tau2 import records_only

KINDS = ("code", "source", "local")
FINAL = "final"  # the last checkpoint: the action, just before it runs
ID_FIELDS = ("order_id", "payment_method_id", "item_ids", "new_item_ids")

Verdict = dict[str, Any]  # {"ok": bool, "wrong_fields": [str], "explanation": str, tokens_in, tokens_out, seconds}

# fmt: off
CONFIGS: dict[str, dict[str, list[str]]] = {
    "none":        {"every_hop": [],         "final": []},
    "end_only":    {"every_hop": [],         "final": ["source"]},
    "code_only":   {"every_hop": ["code"],   "final": ["code"]},
    "every_step":  {"every_hop": ["source"], "final": ["source"]},
    "no_source":   {"every_hop": ["local"],  "final": ["local"]},
    "lightweight": {"every_hop": ["code"],   "final": ["code", "source"]},
}
# fmt: on


def code_check(claim: dict[str, Any], transcript: str) -> Verdict:
    """Flag every ID field whose value never appears in the conversation."""
    bad = set()
    for k in ID_FIELDS:
        vals = claim.get(k) or []
        for v in vals if isinstance(vals, list) else [vals]:
            if v and str(v) not in transcript:
                bad.add(k)
    return {"ok": not bad, "wrong_fields": sorted(bad)}


def check(llm: LLM, kind: str, claim: dict[str, Any], transcript: str, is_action: bool = False) -> Verdict:
    """Run one kind of check on a hand-off, or on the final action when `is_action` is true."""
    if kind == "code":
        start = time.perf_counter()
        verdict = code_check(claim.get("arguments", {}) if is_action else claim, transcript)
        return {**verdict, "tokens_in": 0, "tokens_out": 0, "seconds": round(time.perf_counter() - start, 5)}

    what = "FINAL ACTION TO CHECK" if is_action else "SUMMARY TO CHECK"
    if kind == "source":
        prompt = f"CONVERSATION:\n{transcript}\n\n{what}:\n{json.dumps(claim)}"
    elif kind == "local":
        prompt = f"RECORDS THE AGENT LOOKED UP:\n{records_only(transcript)}\n\n{what}:\n{json.dumps(claim)}"
    else:
        raise ValueError(f"unknown check kind {kind!r}")
    reply = llm.ask_json(CHECK, prompt, stub={"ok": True, "wrong_fields": []})
    v = reply.data
    return {
        "ok": v.get("ok") is not False,
        "wrong_fields": v.get("wrong_fields") or [],
        "explanation": v.get("explanation", ""),
        **reply.usage(),
    }


def first_flag(trace: dict[str, Any], config: str) -> tuple[int | str, str, Verdict] | None:
    """The first failed check under `config`, as (checkpoint, kind, verdict), or None if the config approves."""
    cfg = CONFIGS[config]
    points = [(h["hop"], h["checks"], cfg["every_hop"]) for h in trace["hops"]]
    points.append((FINAL, trace["final"]["checks"], cfg["final"]))
    for where, checks, kinds in points:
        for kind in kinds:
            if not checks[kind]["ok"]:
                return where, kind, checks[kind]
    return None


def score(
    trace: dict[str, Any], config: str, ignore: Callable[[Verdict], bool] | None = None
) -> tuple[bool, int | str | None, int, dict[str, float]]:
    """Apply one config to a logged trace.

    trace = {"hops": [{"hop": 1, "checks": {kind: verdict}}, ...], "final": {"checks": {kind: verdict}}}
    `ignore(verdict) -> bool` can discard individual failed verdicts (used for the adjusted false-alarm rate).
    Returns (flagged, first checkpoint that flagged, LLM calls, cost). Cost sums tokens and seconds over the
    checks this config runs; checks run one after another, so seconds is the delay the guard adds to one run.
    """
    cfg = CONFIGS[config]
    points = [(h["hop"], h["checks"], cfg["every_hop"]) for h in trace["hops"]]
    points.append((FINAL, trace["final"]["checks"], cfg["final"]))
    first, calls = None, 0
    cost = {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0}
    for where, checks, kinds in points:
        for kind in kinds:
            verdict = checks[kind]
            calls += kind != "code"
            for k in cost:
                cost[k] += verdict.get(k, 0) or 0
            failed = not verdict["ok"] and not (ignore and ignore(verdict))
            if failed and first is None:
                first = where
    return first is not None, first, calls, cost
