"""BROKEN. Expected violation: "2 transfers".

Claims the payout with `put` instead of a conditional write. A plain write
always succeeds, so there is no answer to believe and no way to discover that
somebody else got there first.

Crash-only, this is indistinguishable from the reference: the claim is durable
before the transfer, which is all a crash can test. Add a takeover and the
plain write quietly overwrites the other worker's record, so both workers
believe they own the payout.
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

    existing = store.get(state_key)
    if existing == COMPLETED:
        return COMPLETED
    if existing in (NEEDS_REVIEW, IN_PROGRESS):
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    store.put(state_key, IN_PROGRESS)

    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    store.put(state_key, COMPLETED)
    return COMPLETED
