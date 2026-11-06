"""BROKEN. Expected violation: "at most one".

Records the outcome but never records the intent, so a restarted process cannot
distinguish "not started" from "died at the transfer". It assumes the former
and transfers again.
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
    if state is not None:
        return state

    try:
        legacy.transfer(amount_cents=amount_cents)
    except TransferTimeout:
        store.put(state_key, "needs_review")
        return "needs_review"

    store.put(state_key, "completed")
    return "completed"
