"""The reported numbers, recomputed from the saved results in results/. If one of these fails, a reported number
no longer follows from the data."""

import pytest

from blindspots.analysis import RESULTS, summarize


@pytest.fixture(scope="module")
def s():
    return summarize(RESULTS)


def kn(d):
    return d["k"], d["n"]


def test_headline_planted_vs_real(s):
    assert kn(s["headline"]["planted_caught"]) == (306, 306)
    assert kn(s["headline"]["real_caught"]) == (43, 79)


def test_experiment_1_lab(s):
    lab = s["lab"]
    assert lab["cases"] == 58 and lab["clean"]["correct"] == 54
    assert (lab["handoff_faults"]["applied"], lab["handoff_faults"]["reached_end"]) == (393, 306)
    assert (lab["confirmed_faults"]["planted"], lab["confirmed_faults"]["took_hold"]) == (50, 12)
    c = lab["configs"]
    assert kn(c["code_only"]["caught"]) == (102, 306)
    assert kn(c["no_source"]["caught"]) == (283, 306) and kn(c["no_source"]["confirmed_caught"]) == (8, 12)
    assert kn(c["end_only"]["false_alarms"]) == (4, 54)
    assert kn(c["every_step"]["false_alarms"]) == (26, 54)
    assert kn(c["every_step"]["false_alarms_adjusted"]) == (11, 54)
    assert kn(c["no_source"]["false_alarms"]) == (28, 54)
    assert c["end_only"]["cost_per_1000_runs"] == 0.86 and c["every_step"]["cost_per_1000_runs"] == 4.18
    assert kn(c["every_step"]["right_step"]) == (295, 318)
    assert kn(c["no_source"]["by_position"]["1"]) == (53, 66)


def test_experiment_2_wild(s):
    w = s["wild"]
    assert w["kept"] == {"mistakes": 79, "correct": 119}
    assert kn(w["full"]["false_alarms"]) == (13, 119)
    assert kn(w["records"]["caught"]) == (19, 79) and kn(w["records"]["false_alarms"]) == (21, 119)
    ex = w["explanations"]
    assert (ex["missed_cites_request"], ex["missed_cites_confirmation"], ex["missed"]) == (33, 25, 36)


def test_experiment_2b_skeptic(s):
    sk = s["skeptic"]
    assert (sk["usable"], sk["mistakes"], sk["correct"]) == (178, 73, 105)
    assert [sk["caught"][k]["k"] for k in ("original", "baseline", "skeptic")] == [39, 39, 39]
    assert [sk["false_alarms"][k]["k"] for k in ("original", "baseline", "skeptic")] == [10, 7, 4]
    assert kn(sk["clue_in_chat"]) == (51, 73)
    assert kn(sk["caught_with_clue"]["original"]) == (38, 51)
    assert kn(sk["caught_without_clue"]["original"]) == (1, 22)
    assert sk["run_to_run_flips"] == 17
