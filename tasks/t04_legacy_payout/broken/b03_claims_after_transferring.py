"""BROKEN. Expected violation: "at most one".

Has a claim marker and writes it in the wrong order, after the transfer it is
meant to guard. The marker then only ever records transfers that already
completed successfully, which is precisely the case that needed no marker.
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
    claim_key = f"payout:{payout_id}:claim"

    settled = store.get(state_key)
    if settled is not None:
        return settled
    if store.get(claim_key) is not None:
        store.put(state_key, "needs_review")
        return "needs_review"

    try:
        legacy.transfer(amount_cents=amount_cents)
    except TransferTimeout:
        store.put(claim_key, "yes")
        store.put(state_key, "needs_review")
        return "needs_review"

    store.put(claim_key, "yes")
    store.put(state_key, "completed")
    return "completed"
