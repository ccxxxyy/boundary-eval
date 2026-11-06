"""BROKEN. Expected violation: "the promise that the money moved exactly once is false".

Treats a timeout as success on the grounds that the request probably landed.
Sometimes it did. When it did not, the supplier is never paid and the system
records the payout as completed, so nobody ever looks at it again.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    state_key = f"payout:{payout_id}:state"
    state = store.get(state_key)
    if state in ("completed", "needs_review"):
        return state
    if state == "attempting":
        store.put(state_key, "needs_review")
        return "needs_review"

    store.put(state_key, "attempting")
    try:
        legacy.transfer(amount_cents=amount_cents)
    except TransferTimeout:
        pass  # the request almost certainly landed

    store.put(state_key, "completed")
    return "completed"
