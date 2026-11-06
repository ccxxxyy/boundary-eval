"""Known-correct, and a different mechanism: an explicit fencing token.

Instead of treating the claim as a lock whose answer must be believed, this
mints a token for every run and writes it into the claim. The token is then
re-checked immediately before and after the transfer: if the value in the
store is no longer this run's token, somebody else owns the payout and this
run must not touch the bank.

The shape is different from the reference - a token per run rather than a
single `in_progress` marker, a re-read after the transfer rather than a
single conditional write - so it is here to show the grader judges the
invariant and not a particular idiom.
"""

from __future__ import annotations

from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout

COMPLETED = "completed"
NEEDS_REVIEW = "needs_review"


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id,
) -> str:
    state_key = f"payout:{payout_id}:state"

    current = store.get(state_key)
    if current == COMPLETED:
        return COMPLETED
    if current is not None:
        # Either an escalation, or a token from a run that never finished. In
        # both cases the outcome of the transfer is unknown and unknowable.
        if current != NEEDS_REVIEW:
            store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    token = f"run:{new_id()}"
    if not store.compare_and_set(state_key, None, token):
        # Fenced before even starting: another worker holds the payout.
        return COMPLETED if store.get(state_key) == COMPLETED else NEEDS_REVIEW

    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        store.compare_and_set(state_key, token, NEEDS_REVIEW)
        return NEEDS_REVIEW

    # Only the run that still owns the token may record success. If a takeover
    # replaced it, that worker has already decided the outcome.
    if store.compare_and_set(state_key, token, COMPLETED):
        return COMPLETED
    return COMPLETED if store.get(state_key) == COMPLETED else NEEDS_REVIEW
