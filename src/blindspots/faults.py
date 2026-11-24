"""Planted faults for Experiment 1.

Hand-off faults overwrite fields in a structured hand-off between two agents:
  easy    an order ID that never appears in the conversation (a rule check can catch it)
  medium  the customer's other real order, with that order's own items (coherent, nothing looks broken)
  hard    another item from the same order, or the customer's other payment method

A "confirmed" fault is planted in the conversation instead: the support agent reads back a wrong change and the
customer agrees. That is the pattern behind most real mistakes.
"""

from __future__ import annotations

import copy
import dataclasses
import random
from typing import Any

from blindspots.tau2 import HANDOFF_FIELDS, LabCase, last_message_index

HANDOFF_LEVELS = ("easy", "medium", "hard")

Handoff = dict[str, Any]

_VERBS = {
    "cancel_pending_order": "cancel",
    "return_delivered_order_items": "return",
    "exchange_delivered_order_items": "exchange",
    "modify_pending_order_items": "change the items in",
    "modify_pending_order_payment": "change the payment method of",
    "modify_pending_order_address": "change the shipping address of",
}


def inject(handoff: Handoff, case: LabCase, level: str, rng: random.Random) -> tuple[Handoff | None, str]:
    """Return (corrupted copy of the hand-off, description), or (None, why this level can't apply to the case)."""
    h = copy.deepcopy(handoff)
    oid = h.get("order_id")

    if level == "easy":
        while True:
            fake = "#W" + "".join(rng.choice("0123456789") for _ in range(7))
            if fake not in case.transcript:
                break
        h["order_id"] = fake
        return h, f"order_id {oid} -> {fake} (not in conversation)"

    if level == "medium":
        n = len(h.get("item_ids") or [])
        others = [o for o in case.customer_orders if o != oid and (n == 0 or len(case.items_by_order.get(o, [])) >= n)]
        if not oid or not others:
            return None, "no other looked-up order to swap in"
        new = rng.choice(others)
        h["order_id"] = new
        if n:
            h["item_ids"] = case.items_by_order[new][:n]
        return h, f"order {oid} -> {new} with its own items (coherent wrong order)"

    if level == "hard":
        items = h.get("item_ids") or []
        same_order = [i for i in case.items_by_order.get(oid, []) if i not in items]
        if items and same_order:
            old = items[0]
            h["item_ids"] = [rng.choice(same_order)] + items[1:]
            return h, f"item {old} -> {h['item_ids'][0]} (other item in the same order)"
        pm = h.get("payment_method_id")
        other_pm = [p for p in case.payment_methods if p != pm]
        if pm and other_pm:
            h["payment_method_id"] = rng.choice(other_pm)
            return h, f"payment {pm} -> {h['payment_method_id']} (customer's other method)"
        return None, "no plausible item or payment swap"

    raise ValueError(f"unknown fault level {level!r}")


def planted_field(description: str) -> str | None:
    """Which hand-off field a fault description says was changed (used for the 'right reason' analysis)."""
    for prefix, name in (("order", "order_id"), ("item", "item_ids"), ("payment", "payment_method_id")):
        if description.startswith(prefix) or f": {prefix}" in description:
            return name
    return None


def correct_handoff(case: LabCase) -> Handoff:
    """The hand-off a perfect intake agent would write (also the dry-run stub)."""
    a = case.correct_action
    h: Handoff = {"action": a["name"]}
    h.update({k: a["arguments"].get(k, [] if k.endswith("ids") else None) for k in HANDOFF_FIELDS})
    h.update(user_authenticated=True, user_confirmed=True, order_status="delivered")
    return h


def describe(h: Handoff) -> str:
    """A change in plain words, the way a support agent would read it back to the customer."""
    parts = [f"{_VERBS.get(h.get('action'), h.get('action'))} order {h.get('order_id')}"]
    if h.get("item_ids"):
        parts.append(f"items {', '.join(h['item_ids'])}")
    if h.get("new_item_ids"):
        parts.append(f"replacing them with {', '.join(h['new_item_ids'])}")
    if h.get("payment_method_id"):
        parts.append(f"using {h['payment_method_id']}")
    if h.get("reason"):
        parts.append(f"reason: {h['reason']}")
    return "; ".join(parts)


def confirmed_case(case: LabCase, rng: random.Random) -> tuple[LabCase | None, str]:
    """A copy of the case whose conversation ends with the agent proposing a wrong change and the customer agreeing.

    The wrong order has the same status as the right one, so the store policy alone can't rule it out.
    """
    right = case.correct_action["arguments"].get("order_id")
    st = case.status_by_order
    same_status = dataclasses.replace(
        case, customer_orders=[o for o in case.customer_orders if st.get(o) == st.get(right)]
    )
    for level in ("medium", "hard"):  # a coherent wrong order first, else another item or payment method
        wrong, fault = inject(correct_handoff(case), same_status, level, rng)
        if wrong is not None:
            break
    else:
        return None, "no plausible wrong change to propose"
    last = last_message_index(case.transcript)
    extra = (
        f"\n[{last + 1}] assistant: Just to confirm before I submit it: I will {describe(wrong)}. Shall I proceed?"
        f"\n[{last + 2}] user: Yes, please go ahead."
    )
    return dataclasses.replace(case, transcript=case.transcript + extra), f"confirmed in conversation: {fault}"
