# Saved results

The outputs of the final runs. Every reported number is recomputed from these files by `blindspots analyze`
(`make reproduce`), which also writes `summary.json`. See [docs/METHODS.md](../docs/METHODS.md) for how they were made.

## `lab/`: Experiment 1

**`lab_results.csv`** has one row per run: 58 clean runs, plus every planted fault, including ones that couldn't apply
(`applied = False`).

| Column | Meaning |
|---|---|
| `case_id` | `task<id>_<agent model of the source recording>` |
| `level` | `clean`, `easy`, `medium`, `hard` or `confirmed` |
| `position` | hand-off the fault was planted in (1, 2, 4); 0 for `confirmed`; empty for `clean` |
| `applied` | whether the fault could be planted in this case |
| `fault` | what was changed, in words |
| `took` | confirmed faults: did the intake agent adopt the wrong read-back? |
| `final_correct` | the final action equals the correct action |
| `reached_end` | a wrong change would actually have been written to the database |
| `expected_where` | the checkpoint a perfect step-by-step guard would flag first |
| `<config>_flag` | did this guard configuration flag the run? |
| `<config>_where` | the first checkpoint that flagged (`1`–`4` or `final`) |
| `<config>_calls`, `_tokens_in`, `_tokens_out`, `_seconds` | the configuration's LLM calls and cost for this run |

**`lab_traces.jsonl`** has one line per applied run, in the same order as the applied CSV rows: every hand-off, each
agent's note, and every check's verdict (`ok`, `wrong_fields`, `explanation`, tokens, seconds) at every checkpoint.

## `wild/`: Experiment 2

**`wild_results.csv`** has one row per sampled action (120 mistake candidates and 120 correct candidates).

| Column | Meaning |
|---|---|
| `case_id` | `task<id>_<agent model>_t<trial>_m<message index>`. Not unique on its own: pair it with `action` |
| `candidate` | the outcome filter's label: `mistake` or `correct` |
| `adjudicator` | `mistake`, `acceptable` or `unclear` (`gpt-6.2-sol`, sees the secret goal) |
| `kept` | the filter and the adjudicator agree |
| `full_flag` / `records_flag` | did the checker (full chat / records only) flag it? Kept cases only |
| `adjudicator_reason`, `full_explanation` | the written justifications |
| `action` | the tool call under review (JSON) |

## `skeptic/`: Experiment 2b

**`skeptic_results.csv`** has one row per kept case (197; one failed call): `original_flag` (from Experiment 2),
`baseline_flag` and `skeptic_flag` with their explanations, and `clue` / `clue_evidence` for mistakes. 19 rows were
checked against the wrong action and are dropped by the analysis. See quirk 3 in METHODS.

## `archive/`

Outputs of the earlier three-agent pilot and smoke tests. Kept for the record; not part of the reported results.
