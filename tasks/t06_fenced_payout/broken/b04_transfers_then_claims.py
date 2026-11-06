"""BROKEN. Expected violation: "2 transfers".

Transfers first and records afterwards. There is no window in which a claim
exists without the money having moved, which is what makes this look tidy, and
it is wrong in both fault models: a crash between the transfer and the write
loses all knowledge of the payout, and a takeover simply pays twice because
neither worker ever looked for a claim.
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

    existing = store.get(state_key)
    if existing in (COMPLETED, NEEDS_REVIEW):
        return existing

    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    store.put(state_key, COMPLETED)
    return COMPLETED
