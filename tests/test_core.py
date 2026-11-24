"""Unit tests for the logic the results depend on. None of them call a model or need the benchmark download."""

import random

import pytest

from blindspots.analysis import pair_skeptic
from blindspots.faults import inject, planted_field
from blindspots.guards import code_check, score
from blindspots.llm import LLM, _parse_json
from blindspots.stats import mcnemar_exact, rate, wilson
from blindspots.tau2 import LabCase, norm, records_only, same_action

TRANSCRIPT = (
    "[0] user: Please return the kettle from order #W1111111.\n"
    '[1] tool result: {"order_id": "#W1111111", "items": [{"item_id": "100"}, {"item_id": "200"}]}\n'
    '[2] tool result: {"order_id": "#W2222222", "items": [{"item_id": "300"}]}'
)
CASE = LabCase(
    case_id="task0_test",
    transcript=TRANSCRIPT,
    correct_action={
        "name": "return_delivered_order_items",
        "arguments": {"order_id": "#W1111111", "item_ids": ["100"]},
    },
    customer_orders=["#W1111111", "#W2222222"],
    payment_methods=["card_1", "gift_card_2"],
    items_by_order={"#W1111111": ["100", "200"], "#W2222222": ["300"]},
)
HANDOFF = {"action": "return_delivered_order_items", "order_id": "#W1111111", "item_ids": ["100"]}


# ------------------------------------------------------------------------------------------------ tau2 helpers


def test_actions_compare_regardless_of_list_order():
    assert norm({"item_ids": ["b", "a"]}) == norm({"item_ids": ["a", "b"]})
    a = {"name": "x", "arguments": {"item_ids": ["2", "1"], "extra": 1}}
    assert same_action(a, {"name": "x", "arguments": {"item_ids": ["1", "2"]}})
    assert not same_action(a, {"name": "y", "arguments": {"item_ids": ["1", "2"]}})
    assert not same_action(None, {"name": "x", "arguments": {}})


def test_records_only_drops_what_the_customer_said():
    kept = records_only(TRANSCRIPT)
    assert "kettle" not in kept and kept.count("tool result") == 2


# ------------------------------------------------------------------------------------------------------ faults


def test_easy_fault_invents_an_order_id_absent_from_the_conversation():
    bad, desc = inject(HANDOFF, CASE, "easy", random.Random(0))
    assert bad["order_id"] not in TRANSCRIPT and bad["item_ids"] == ["100"]
    assert HANDOFF["order_id"] == "#W1111111", "inject must not mutate its input"
    assert planted_field(desc) == "order_id"


def test_medium_fault_swaps_in_another_real_order_with_its_own_items():
    bad, desc = inject(HANDOFF, CASE, "medium", random.Random(0))
    assert bad["order_id"] == "#W2222222" and bad["item_ids"] == ["300"]
    assert code_check(bad, TRANSCRIPT)["ok"], "a coherent wrong order must pass the rule check"
    assert planted_field(desc) == "order_id"


def test_hard_fault_picks_another_item_from_the_same_order():
    bad, desc = inject(HANDOFF, CASE, "hard", random.Random(0))
    assert bad["order_id"] == "#W1111111" and bad["item_ids"] == ["200"]
    assert planted_field(desc) == "item_ids"


def test_fault_that_cannot_apply_returns_none():
    lonely = LabCase(case_id="t", transcript="", correct_action=CASE.correct_action, customer_orders=["#W1111111"])
    assert inject(HANDOFF, lonely, "medium", random.Random(0)) == (None, "no other looked-up order to swap in")
    with pytest.raises(ValueError):
        inject(HANDOFF, CASE, "nonsense", random.Random(0))


# ------------------------------------------------------------------------------------------------------ guards


def test_code_check_flags_only_ids_missing_from_the_conversation():
    assert code_check(HANDOFF, TRANSCRIPT) == {"ok": True, "wrong_fields": []}
    v = code_check({**HANDOFF, "order_id": "#W9999999", "payment_method_id": "card_1"}, TRANSCRIPT)
    assert v == {"ok": False, "wrong_fields": ["order_id", "payment_method_id"]}


def _verdict(ok, fields=(), tokens=0):
    return {"ok": ok, "wrong_fields": list(fields), "tokens_in": tokens, "tokens_out": 0, "seconds": 1.0}


def _trace(hop_source_ok, final_source_ok):
    hops = [
        {
            "hop": i + 1,
            "checks": {
                "code": _verdict(True),
                "source": _verdict(ok, ["policy_allowed"], 10),
                "local": _verdict(True, tokens=10),
            },
        }
        for i, ok in enumerate(hop_source_ok)
    ]
    final = {
        "checks": {
            "code": _verdict(True),
            "source": _verdict(final_source_ok, ["order_id"], 10),
            "local": _verdict(True, tokens=10),
        }
    }
    return {"hops": hops, "final": final}


def test_configs_are_scored_on_the_same_trace():
    trace = _trace([True, False, True, True], final_source_ok=False)
    assert score(trace, "none")[:3] == (False, None, 0)
    assert score(trace, "end_only")[:3] == (True, "final", 1)
    assert score(trace, "every_step")[:3] == (True, 2, 5)  # first flag at hop 2; 4 hops + final
    assert score(trace, "code_only")[:3] == (False, None, 0)  # code checks are free
    assert score(trace, "every_step")[3] == {"tokens_in": 50, "tokens_out": 0, "seconds": 5.0}


def test_ignore_discards_individual_failed_verdicts():
    trace = _trace([True, False, True, True], final_source_ok=True)
    only_policy = lambda v: v["wrong_fields"] == ["policy_allowed"]  # noqa: E731
    assert score(trace, "every_step")[0] is True
    assert score(trace, "every_step", ignore=only_policy)[0] is False


# ------------------------------------------------------------------------------------------------------- stats


def test_wilson_interval_matches_reference_values():
    lo, hi = wilson(43, 79)
    assert round(lo, 1) == 43.5 and round(hi, 1) == 65.0
    assert wilson(0, 0) != wilson(0, 0)  # nan when there is no data
    assert str(rate([True, True, False, False])) == "2/4 = 50% (15-85)"


def test_mcnemar_uses_only_discordant_pairs():
    assert mcnemar_exact([True, False], [True, False]) == {"only_a": 0, "only_b": 0, "p_value": 1.0}
    r = mcnemar_exact([False] * 10, [True] * 10)
    assert r["only_b"] == 10 and r["p_value"] == pytest.approx(2 / 2**10, abs=1e-4)


# --------------------------------------------------------------------------------------------- LLM and pairing


def test_json_is_found_inside_prose_or_code_fences():
    assert _parse_json('Sure!\n```json\n{"ok": false}\n```') == {"ok": False}
    with pytest.raises(ValueError):
        _parse_json("no json here")


def test_dry_run_returns_the_stub_and_counts_calls():
    llm = LLM("anthropic", "any-model", dry_run=True)
    assert llm.ask_json("system", "user", stub={"ok": True}).data == {"ok": True}
    assert llm.calls == 1 and llm.failures == 0


def test_skeptic_rows_checked_against_the_wrong_action_are_dropped():
    a1, a2 = '{"name": "x", "arguments": {"n": 1}}', '{"name": "x", "arguments": {"n": 2}}'
    labels = [
        {"case_id": "c1", "kept": "True", "action": a1},
        {"case_id": "c1", "kept": "True", "action": a2},
        {"case_id": "c2", "kept": "False", "action": a1},
        {"case_id": "c3", "kept": "True", "action": a1},
    ]
    # the old run looked actions up by case_id alone, so both c1 labels were checked against a2
    rows = [{"case_id": "c1", "action": a2}, {"case_id": "c1", "action": a2}, {"case_id": "c3", "action": a1}]
    kept = pair_skeptic(labels, rows)
    assert [(lab["action"], row["case_id"]) for lab, row in kept] == [(a2, "c1"), (a1, "c3")]
