# Methods

This document describes exactly how every reported number was produced. The code it refers to is in
`src/blindspots/`; every number can be recomputed with `make reproduce`.

## Contents

1. [Data](#1-data)
2. [Experiment 1: in the lab](#2-experiment-1-in-the-lab)
3. [Experiment 2: in the wild](#3-experiment-2-in-the-wild)
4. [Experiment 2b: a skeptical prompt and the clue judge](#4-experiment-2b-a-skeptical-prompt-and-the-clue-judge)
5. [Explainability analyses](#5-explainability-analyses)
6. [Statistics](#6-statistics)
7. [Models, cost and run record](#7-models-cost-and-run-record)
8. [Known quirks in the saved results](#known-quirks-in-the-saved-results)
9. [Earlier pilot](#9-earlier-pilot)

## 1. Data

[τ²-bench](https://github.com/sierra-research/tau2-bench) (Sierra Research, MIT), retail domain, commit `768f3d8`.

- 114 customer-service tasks. Each has a store policy (`data/tau2/domains/retail/policy.md`), an order database, read
  tools and seven **write tools** (cancel, exchange, return, modify items / address / payment, modify user address).
- A simulated customer (GPT-4.1) follows a **secret script** (`user_scenario.instructions`) that the agent never sees.
  Each task also stores the correct database actions; the benchmark scores a conversation as pass/fail by comparing the
  final database.
- Recorded conversations ship with the benchmark in `data/tau2/results/final/*_retail_*.json`: 4 agent models (Claude
  3.7 Sonnet, GPT-4.1, GPT-4.1 mini, o4-mini) × 114 tasks × 4 trials = 1,824 conversations.

Conversations are rendered as numbered plain text (`tau2.render`): `[i] user: …`, `[i] tool result: {…}`,
`[i] assistant calls tool({…})`. A **records-only** view keeps just the tool-result lines (`tau2.records_only`).

## 2. Experiment 1: in the lab

Code: `experiments/lab.py`, `faults.py`, `guards.py`. Output: `results/lab/`.

### Cases (`tau2.build_lab_cases`)

For each task, take the first recording (in file order) that **passed**, whose correct solution makes **exactly one**
change, and whose agent's **first write call equals that change**. Cut the conversation just before that call. 58 of
114 tasks qualify; all 58 are used (shuffled with seed 0). From the tool results before the cut, record the customer's
orders, payment methods, each looked-up order's items and status.

### The chain

```
conversation → 1 intake → 2 verifier → 3 pricing → 4 policy → planner → final action
              hand-off 1   hand-off 2   hand-off 3   hand-off 4
```

All agents are `claude-haiku-5-5`. Prompts are in `prompts.py`.

- **Intake** reads the conversation and writes a structured hand-off (action, IDs, address fields,
  `user_authenticated`, `user_confirmed`, `order_status`). If the support agent read back a final summary and the
  customer confirmed it, that summary is the agreed change.
- **Verifier** (records + hand-off) adds `ownership_ok`. **Pricing** (records + hand-off) adds `price_difference`.
  **Policy** (store policy + hand-off) adds `policy_allowed`. **Planner** writes the final tool call, or `none` if policy
  refused.
- Only intake sees the conversation. Each agent's free-text note is logged but **not forwarded**: a note repeating an
  original ID would give a planted fault away.

### Planted faults (`faults.py`)

| Level | What changes | Designed to test |
|---|---|---|
| easy | `order_id` → a random `#W…` ID that doesn't appear in the conversation | whether rules catch invented IDs |
| medium | the customer's **other** looked-up order, **with that order's own items** | a coherent wrong order: nothing looks broken |
| hard | another item from the same order; if impossible, the customer's other payment method | a subtle, plausible change |
| confirmed | in the **conversation**: the agent reads back a wrong change (medium, else hard, restricted to orders with the same status so policy can't block it) and the customer replies "Yes, please go ahead." | the pattern behind real mistakes |

Hand-off faults are planted at hand-offs 1, 2 and 4. The clean prefix up to the planted hand-off is reused, and the
rest of the chain is rerun from there. A fault that can't apply to a case (e.g. no other order to swap in) is recorded
as not applied. Each fault uses its own seeded RNG (`"{seed}-{case}-{level}-{position}"`), so runs are reproducible.

### Checks and guard configurations (`guards.py`)

Three kinds of check, each run on **every** hand-off and on the final action:

| Kind | Sees | Cost |
|---|---|---|
| `code` | every ID field must appear as a substring of the conversation | free |
| `source` | the full conversation + the hand-off or action (prompt `CHECK`) | 1 LLM call |
| `local` | the records only + the hand-off or action (prompt `CHECK`) | 1 LLM call |

All verdicts are logged in a trace. Six configurations are then **scored from the same traces**:

| Config | At every hand-off | At the final action |
|---|---|---|
| `none` | – | – |
| `end_only` | – | source |
| `code_only` | code | code |
| `every_step` | source | source |
| `no_source` | local | local |
| `lightweight` | code | code + source |

A configuration **flags** a run if any check it includes fails; **where** is the first failing checkpoint. Tokens and
seconds are summed over the checks it runs (checks run sequentially, so seconds is the added delay).

### Metrics (`analysis.summarize_lab`)

- **Caught:** among hand-off faults that **reached the final action** (the agents didn't stop them), the share a
  config flags. Faults the agents stopped are excluded, because there is nothing left for a guard to catch.
- **Confirmed caught:** the same, for confirmed faults that reached the end.
- **False alarms:** flags on the 54 clean runs whose final action was correct.
- **Adjusted false alarms:** the same, ignoring failed checks whose `wrong_fields` contain only `policy_allowed`. The
  full-chat check at hand-off 4 often disputes this internal pipeline field, which the conversation can't confirm. This
  changes `every_step` from 48% to 20%; catch rates are unaffected.
- **Right step:** among caught runs, the share whose first flag is at the hand-off where the fault was planted
  (hand-off 1 for confirmed faults).
- **Cost per 1,000 runs:** average tokens per clean run × Claude Haiku 5.5 list prices ($0.10 / $0.50 per million
  input/output tokens). **Delay:** average summed check latency per clean run. It was measured while many runs shared
  the API in parallel, so treat it as indicative.

## 3. Experiment 2: in the wild

Code: `experiments/wild.py`. Output: `results/wild/wild_results.csv`.

1. **Outcome filter** (`tau2.real_action_pool`). Over all 1,824 recordings, take every write call that succeeded
   (calls the shop's system rejected are skipped).
   - *Mistake candidate:* not one of the task's expected changes, in a conversation that **failed**.
   - *Correct candidate:* one of the expected changes, in a conversation that **passed**.

   The pool is 352 mistake and 1,902 correct candidates; 120 of each are sampled (seed 0).
2. **Adjudicator** (`gpt-6.2-sol`). Sees the customer's **secret goal**, the conversation up to the action, and the
   action. Answers `mistake`, `acceptable` or `unclear`.
3. **Keep only agreement:** mistake candidates labelled `mistake`, and correct candidates labelled `acceptable`.
   Result: 79 real mistakes and 119 correct actions. The adjudicator judged 41 of 120 mistake candidates acceptable, so
   the filter alone is wrong about a third of the time. It judged 1 of 120 correct candidates a mistake.
4. **Checker** (`claude-haiku-5-5`, prompt `CHECK`, the same as Experiment 1). Sees what a production checker would see,
   the conversation (`full`) or the records only (`records`), plus the action. **Never the secret goal.**

## 4. Experiment 2b: a skeptical prompt and the clue judge

Code: `experiments/skeptic.py`. Output: `results/skeptic/skeptic_results.csv`. Same cases and labels as Experiment 2;
nothing is relabelled.

- **Baseline:** the original `CHECK` prompt, run again. This measures run-to-run noise.
- **Skeptic:** same model and inputs; the prompt (`SKEPTIC`) says the customer's "yes" is not proof, and asks for a check
  against what the customer *first* asked for and against the records.
- **Clue judge** (`gpt-6.2-sol`, prompt `CLUE`), for each real mistake, given the adjudicator's reason: *could a reviewer
  who sees only the conversation have known this was wrong?* `yes` / `no` plus evidence.

178 cases are usable: 73 mistakes and 105 correct (see [quirk 3](#known-quirks-in-the-saved-results)).

## 5. Explainability analyses

- **Why the checker approves** (`analysis.summarize_wild`). For the 36 real mistakes the full-chat checker missed, its
  explanation is matched against two keyword rules: `request|asked|wants|wanted` (it justifies approval by the
  customer's request: 33/36) and `confirm` (it cites the customer's confirmation: 25/36). These rules are deliberately
  simple and approximate. Read the explanations themselves in the explorer.
- **Right for the right reason** (Experiment 1). For each caught run, take the first failing check under a config and
  ask whether its `wrong_fields` names the planted field (`order…`, `item…` or `payment…`). Results: `end_only` 100%,
  `every_step` 93%, `no_source` 67% (of runs it caught).
- **Clue / no clue** (Experiment 2b): the checker's catch rate split by whether the mistake was detectable from the
  chat at all.
- **Faithfulness.** Stated explanations need not reflect how a model actually decided (Turpin et al., 2023), so the
  keyword counts are treated as what the checker *claims*. They are interpreted together with behaviour that doesn't
  depend on the explanations: the clue split, and the skeptical prompt failing to change the catch rate.

## 6. Statistics

- Proportions are reported with **Wilson 95% intervals** (`stats.wilson`).
- **Skeptic vs. baseline** is a paired comparison on the same cases: an **exact two-sided McNemar test** on discordant
  pairs (`stats.mcnemar_exact`). Mistakes: p = 1.0; correct actions: p = 0.51.
- Each experiment was run once (after dry runs and small smoke tests) because of API budget. Run-to-run variation is
  measured directly in Experiment 2b: 17 of 178 verdicts changed between two identical runs, while totals stayed the
  same.

## 7. Models, cost and run record

| Role | Model | Calls (approx.) |
|---|---|---|
| Agents and checkers, Exp 1 | Anthropic `claude-haiku-5-5` | ~5,600 |
| Checker, Exp 2 and 2b | Anthropic `claude-haiku-5-5` | ~790 |
| Adjudicator, clue judge | OpenAI `gpt-6.2-sol` | ~315 |

About 6,700 calls in total. The adjudicator is from a different model family than the checker, to reduce
self-preference bias. Gemini (Vertex AI) is supported by the client but wasn't used for the reported results.

The final runs were made with the project's original single-file scripts. The code was then refactored into this
package **without changing behaviour that affects results**. Prompts are byte-identical. Case construction, fault
injection and the Experiment 2 sample were verified to reproduce the original outputs exactly: the same 58 cases, the
same faults, and the same 240 sampled actions. Deliberate changes:

- Experiment 2 and 2b now match labels on `(case_id, action)` rather than `case_id` alone (quirk 3).
- Experiment 1 traces now record `position` (quirk 1).
- The `wild` command's defaults (`--n 120`, OpenAI adjudicator) now match the reported run.
- Retries are limited to API and parsing errors, instead of catching every exception.

## Known quirks in the saved results

1. **Experiment 1 traces have no `position` field.** They were written in the same order as the CSV rows with
   `applied == True`, so `analysis.load_lab` matches them by order and checks that `case_id` and `level` agree on every
   row.
2. **`policy_allowed` false alarms** inflate `every_step`'s raw false-alarm rate (48%); see the adjusted metric above.
3. **Parallel tool calls share a `case_id`.** GPT agents sometimes make two write calls in one message, so `case_id`
   (task, model, trial, message index) is not unique. The skeptic run looked actions up by `case_id` alone, so 19 rows
   were checked against the *other* action from the same message. `analysis.pair_skeptic` recovers the label each row
   was run for (rows were written in label order) and drops those 19, leaving 178. The Experiment 2 results are not
   affected: all 240 rows there carry distinct `(case_id, action)` pairs.
4. **One correct case is missing from the skeptic results** (an API call failed), so the skeptic CSV has 197 rows for 198
   kept labels.
5. The explanation keyword counts are approximate (section 5).

## 9. Earlier pilot

A three-agent version of Experiment 1 (intake → policy → planner), with no verifier or pricing agent, showed that
planted errors spread (95% reached the end), that full-context checkers catch ~99%, that records-only checkers are
weaker with ~20% false alarms, and that rules catch missing fields but not plausible wrong values. It shaped the fault
design: coherent medium faults, no leaking free text, address fields. Its outputs are kept in `results/archive/` for the
record. They are not part of the reported results, and the code that produced them is not part of this package.
