"""BROKEN. Expected violation: "2 transfers".

The claim-before-act pattern, implemented exactly as the textbook describes
it, with one detail missing: the return value of `compare_and_set` is thrown
away.

Under a crash-only fault model this code is flawless. Kill the process at any
point and the surviving claim stops the redelivery from transferring again.
But a worker that lost the claim to a takeover still walks into
`legacy.transfer`, and the supplier is paid twice.
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

    store.compare_and_set(state_key, None, IN_PROGRESS)

    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    store.put(state_key, COMPLETED)
    return COMPLETED
