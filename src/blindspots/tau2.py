"""Reading tau2-bench retail recordings and turning them into the cases both experiments use.

tau2-bench ships recorded conversations for 4 agent models x 114 retail tasks x 4 trials. Each task has a secret
script for the simulated customer and the database actions a correct agent should take.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_TAU2_DIR = Path("data/tau2-bench")
RECORDINGS_GLOB = "data/tau2/results/final/*_retail_*.json"
POLICY_PATH = "data/tau2/domains/retail/policy.md"

# Tools that change the shop's database. Everything else is a read-only lookup.
WRITE_TOOLS = frozenset(
    {
        "cancel_pending_order",
        "exchange_delivered_order_items",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
        "modify_user_address",
        "return_delivered_order_items",
    }
)
ADDRESS_FIELDS = ("address1", "address2", "city", "state", "country", "zip")
HANDOFF_FIELDS = ("order_id", "user_id", "item_ids", "new_item_ids", "payment_method_id", "reason", *ADDRESS_FIELDS)

Action = dict[str, Any]  # {"name": tool name, "arguments": {...}}


# ----------------------------------------------------------------------------------------------------- loading


def recording_files(tau2_dir: Path) -> list[Path]:
    files = sorted(Path(tau2_dir).glob(RECORDINGS_GLOB))
    if not files:
        raise FileNotFoundError(f"No retail recordings under {tau2_dir}/{RECORDINGS_GLOB}. Run `make data` first.")
    return files


def agent_model(path: Path) -> str:
    """'claude-3-7-sonnet-20250219_retail_default_...json' -> 'claude-3-7-sonnet-20250219'."""
    return path.name.split("_retail")[0]


def policy_text(tau2_dir: Path) -> str:
    return (Path(tau2_dir) / POLICY_PATH).read_text()


# ---------------------------------------------------------------------------------------------- small helpers


def norm(args: dict[str, Any]) -> str:
    """A canonical string for tool arguments, so two actions compare equal regardless of list order."""
    return json.dumps({k: sorted(v) if isinstance(v, list) else v for k, v in args.items()}, sort_keys=True)


def same_action(a: Action | None, b: Action) -> bool:
    """Does `a` do what `b` does? Only `b`'s arguments are compared; extra arguments in `a` are ignored."""
    if not a or a.get("name") != b["name"]:
        return False
    args = a.get("arguments") or {}
    return norm({k: args.get(k) for k in b["arguments"]}) == norm(b["arguments"])


def render(messages: list[dict[str, Any]]) -> str:
    """Recorded messages as numbered plain text, the form every agent and checker reads."""
    lines = []
    for i, m in enumerate(messages):
        if m.get("content"):
            who = "tool result" if m["role"] == "tool" else m["role"]
            lines.append(f"[{i}] {who}: {m['content']}")
        for tc in m.get("tool_calls") or []:
            lines.append(f"[{i}] assistant calls {tc['name']}({json.dumps(tc['arguments'])})")
    return "\n".join(lines)


def records_only(transcript: str) -> str:
    """Only the tool results from a rendered transcript: the records, without anything the customer said."""
    return "\n".join(line for line in transcript.splitlines() if "] tool result:" in line)


def last_message_index(transcript: str) -> int:
    return max(int(m) for m in re.findall(r"^\[(\d+)\]", transcript, re.M))


def _tool_results(messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for m in messages:
        if m["role"] == "tool" and m.get("content", "").startswith("{"):
            try:
                yield json.loads(m["content"])
            except json.JSONDecodeError:
                continue


def _write_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    return [tc for tc in message.get("tool_calls") or [] if tc["name"] in WRITE_TOOLS]


def _expected_writes(sim: dict[str, Any]) -> list[Action]:
    checks = (sim.get("reward_info") or {}).get("action_checks") or []
    return [c["action"] for c in checks if c["action"]["name"] in WRITE_TOOLS]


def _passed(sim: dict[str, Any]) -> bool:
    return (sim.get("reward_info") or {}).get("reward") == 1


# ------------------------------------------------------------------------------------ Experiment 1: lab cases


@dataclass(frozen=True)
class LabCase:
    """A passing conversation cut just before its one database change, plus the records the agent looked up."""

    case_id: str
    transcript: str
    correct_action: Action
    customer_orders: list[str] = field(default_factory=list)
    payment_methods: list[str] = field(default_factory=list)
    items_by_order: dict[str, list[str]] = field(default_factory=dict)
    status_by_order: dict[str, str | None] = field(default_factory=dict)
    trial: int = 0  # which recorded trial the conversation came from
    cut: int = 0  # index of the message holding the write call; the transcript is messages[:cut]


def build_lab_cases(tau2_dir: Path, n: int, seed: int = 0) -> list[LabCase]:
    """One case per retail task (the first passing recording found), shuffled with `seed`, first `n` kept.

    A task qualifies when its correct solution makes exactly one change and the agent's first write call is that
    change, so the conversation up to that call is a clean, agreed request.
    """
    cases: dict[Any, LabCase] = {}
    for path in recording_files(tau2_dir):
        model = agent_model(path)
        for sim in json.loads(path.read_text())["simulations"]:
            if not _passed(sim) or sim["task_id"] in cases:
                continue
            expected = _expected_writes(sim)
            if len(expected) != 1:
                continue
            correct = expected[0]
            msgs = sim["messages"]
            cut = next((i for i, m in enumerate(msgs) if _write_calls(m)), None)
            if cut is None:
                continue
            first = _write_calls(msgs[cut])[0]
            if first["name"] != correct["name"] or norm(first["arguments"]) != norm(correct["arguments"]):
                continue
            before = msgs[:cut]
            orders: list[str] = []
            payments: list[str] = []
            items_by_order: dict[str, list[str]] = {}
            status_by_order: dict[str, str | None] = {}
            for record in _tool_results(before):
                if "orders" in record and "payment_methods" in record:  # a user record
                    orders, payments = list(record["orders"]), list(record["payment_methods"])
                if "order_id" in record and "items" in record:  # an order record
                    items_by_order[record["order_id"]] = [it["item_id"] for it in record["items"]]
                    status_by_order[record["order_id"]] = record.get("status")
            cases[sim["task_id"]] = LabCase(
                case_id=f"task{sim['task_id']}_{model}",
                transcript=render(before),
                correct_action={"name": correct["name"], "arguments": correct["arguments"]},
                customer_orders=orders,
                payment_methods=payments,
                items_by_order=items_by_order,
                status_by_order=status_by_order,
                trial=int(sim["trial"]),
                cut=cut,
            )
    picked = list(cases.values())
    random.Random(seed).shuffle(picked)
    return picked[:n]


# --------------------------------------------------------------------------- Experiments 2, 2b: real actions


@dataclass(frozen=True)
class RealAction:
    """One write call an agent really made, with the conversation up to that point and the customer's goal."""

    case_id: str  # task, agent model, trial, message index. Not unique: one message can hold two write calls.
    transcript: str
    goal: str | None  # the customer's secret script; only the adjudicator and clue judge ever see it
    action: Action

    @property
    def key(self) -> tuple[str, str]:
        """Unique identity of an action: its case_id plus the exact call."""
        return action_key(self.case_id, self.action)


def action_key(case_id: str, action: Action) -> tuple[str, str]:
    return case_id, json.dumps(action, sort_keys=True)


def real_action_pool(tau2_dir: Path) -> tuple[list[RealAction], list[RealAction]]:
    """Every successful write call in the recordings, split by the outcome filter.

    mistake candidate: not one of the expected changes, in a conversation that failed
    correct candidate: one of the expected changes, in a conversation that passed
    Calls the shop's system rejected (an error came back) are skipped: nothing changed.
    """
    mistakes: list[RealAction] = []
    correct: list[RealAction] = []
    for path in recording_files(tau2_dir):
        model = agent_model(path)
        data = json.loads(path.read_text())
        goals = {str(t["id"]): (t.get("user_scenario") or {}).get("instructions") for t in data.get("tasks", [])}
        for sim in data["simulations"]:
            passed = _passed(sim)
            expected = {(a["name"], norm(a["arguments"])) for a in _expected_writes(sim)}
            msgs = sim["messages"]
            for i, m in enumerate(msgs):
                for tc in _write_calls(m):
                    result = next((x for x in msgs[i + 1 :] if x["role"] == "tool"), None) or {}
                    if result.get("error") or (result.get("content") or "").lower().startswith("error"):
                        continue
                    item = RealAction(
                        case_id=f"task{sim['task_id']}_{model}_t{sim['trial']}_m{i}",
                        transcript=render(msgs[:i]),
                        goal=goals.get(str(sim["task_id"])),
                        action={"name": tc["name"], "arguments": tc["arguments"]},
                    )
                    is_expected = (tc["name"], norm(tc["arguments"])) in expected
                    if is_expected and passed:
                        correct.append(item)
                    elif not is_expected and expected and not passed:
                        mistakes.append(item)
    return mistakes, correct


def sample_real_actions(tau2_dir: Path, n: int, seed: int = 0) -> tuple[list[RealAction], list[RealAction], int, int]:
    """Draw up to `n` candidates of each kind. Also returns the pool sizes."""
    mistakes, correct = real_action_pool(tau2_dir)
    rng = random.Random(seed)
    return (
        rng.sample(mistakes, min(n, len(mistakes))),
        rng.sample(correct, min(n, len(correct))),
        len(mistakes),
        len(correct),
    )
