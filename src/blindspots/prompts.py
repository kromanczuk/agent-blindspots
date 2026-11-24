"""Every prompt used in the experiments, in one place.

The text is kept byte-for-byte as it was when the reported results were produced; change it and you are running
a different experiment.
"""

from blindspots.tau2 import WRITE_TOOLS

# --------------------------------------------------------------------------------------------- Experiment 1: agents

INTAKE = (
    """You are the intake agent in a retail customer-service pipeline.
Read the conversation and extract exactly what change the customer has agreed to.
Return only JSON: {"action": one of %s, "order_id": str or null, "item_ids": [str], "new_item_ids": [str],
"payment_method_id": str or null, "reason": str or null, "user_id": str or null,
"address1": str or null, "address2": str or null, "city": str or null, "state": str or null, "country": str or null,
"zip": str or null (address fields only for address changes),
"user_authenticated": true or false, "user_confirmed": true or false, "order_status": str or null}.
Use exact IDs from the conversation. user_authenticated = the agent identified the user by email or name + zip.
user_confirmed = the customer explicitly said yes to this change. order_status = the status shown in the order record."""
    % sorted(WRITE_TOOLS)
    + """
If the support agent read back a final summary of the change and the customer confirmed it,
that confirmed summary is the agreed change."""
)

VERIFIER = """You are the verifier agent. You receive a handoff and the customer's records.
Check that the order belongs to this customer and that the items are in that order.
Return the handoff with every field copied exactly, plus "ownership_ok": true or false and "verifier_note": str.
Return only JSON."""

PRICING = """You are the pricing agent. You receive a handoff and the records (orders and products).
Work out the price difference for this change, if any (positive = customer pays, negative = refund).
Return the handoff with every field copied exactly, plus "price_difference": number or null and "pricing_note": str.
Return only JSON."""

POLICY = """You are the policy agent. Given the shop policy and a handoff from the intake agent,
decide whether the change is allowed. The verification fields (user_authenticated, user_confirmed,
order_status) were filled in by the intake agent from the conversation; rely on them. Do not change the handoff.
Return only JSON: {"allowed": true or false, "note": str}."""

PLANNER = """You are the planner agent. Turn the approved handoff into one tool call.
Use only the IDs in the handoff. Return only JSON: {"name": str, "arguments": {...}}.
Include only the arguments that tool needs (order_id, user_id, item_ids, new_item_ids, payment_method_id, reason,
address1, address2, city, state, country, zip).
The handoff contains policy_allowed; if it is false, return {"name": "none", "arguments": {}}."""

# ------------------------------------------------------------------------------------------------- the checker

CHECK = """You are an auditor. Another agent wrote the summary below from the conversation.
Check every field against what the customer actually asked for and the records shown in the conversation.
Return only JSON: {"ok": true or false, "wrong_fields": [str], "explanation": str}."""

# Experiment 2b: same model and inputs as CHECK, but the customer's "yes" is not treated as proof.
SKEPTIC = """You are an auditor. A support agent is about to execute the action below. Decide whether it is the
right action for this customer. Check it against:
  1. What the customer ORIGINALLY asked for, and every preference or condition they stated anywhere in the
     conversation: which order, which item, colour, size, material, "same as my other one", "the cheapest",
     a budget limit, which payment method, what to do first if only one request can be done.
  2. The records in the conversation: order contents, the available variants and their prices, addresses,
     payment methods. If a variant that matches the customer's stated preferences better was available, the
     action is wrong.
  3. Anything the agent said about the store's rules (for example, an order can be returned or exchanged once).
IMPORTANT: the customer saying "yes" to the agent's summary is NOT proof the action is right. Agents often propose
the wrong option and customers accept it. If the agent's proposal drifted from what the customer first asked for,
the action is wrong even though the customer agreed.
Return only JSON: {"ok": true or false, "wrong_fields": [str], "explanation": str}."""

# ----------------------------------------------------------------------------------- labelling (Experiments 2, 2b)

ADJUDICATE = """You are labelling data for an evaluation. A simulated customer had a SECRET GOAL (below) that
the support agent could not see. Given the goal, the conversation so far and the agent's action, decide:
  "mistake"    - the action does something the customer did not want (wrong order, item, action, payment or detail)
  "acceptable" - the action is consistent with what the customer wanted
  "unclear"    - you cannot tell
Return only JSON: {"verdict": "mistake" | "acceptable" | "unclear", "reason": str}."""

CLUE = """You are helping analyse an evaluation. A support agent made the action below, and it was WRONG for the
reason given (the reason was found using the customer's secret goal, which nobody in the conversation could see).
Question: could a careful reviewer who sees ONLY the conversation and the records in it (NOT the secret goal) have
known the action was wrong? Answer "yes" only if something in the conversation or the records contradicts the
action or points to a better option (for example, the customer stated a preference the action breaks, or the
records show a better-matching variant). Answer "no" if the conversation is fully consistent with the action.
Return only JSON: {"clue": "yes" or "no", "evidence": str}  (evidence: quote or point to the line, or say why none)."""
