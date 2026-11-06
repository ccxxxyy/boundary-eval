"""BROKEN. Expected violation: "2 transfers".

Checks the claim's result, which is more than most code does, and then draws
the wrong conclusion: if the claim was lost the payout must be stuck, so it
takes the claim back and transfers anyway.

This is the "make progress, never get stuck" instinct, and it is the right
instinct against an idempotent API. Against a system with no idempotency key
it is a second payout.
"""

from __future__ import annotations

from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout

IN_PROGRESS = "in_progress"
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

    if store.get(state_key) == COMPLETED:
        return COMPLETED

    if not store.compare_and_set(state_key, None, IN_PROGRESS):
        current = store.get(state_key)
        if current == COMPLETED:
            return COMPLETED
        # Someone claimed it and may be gone. Take it over so the payout is
        # not stuck forever.
        store.put(state_key, IN_PROGRESS)

    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    store.put(state_key, COMPLETED)
    return COMPLETED
