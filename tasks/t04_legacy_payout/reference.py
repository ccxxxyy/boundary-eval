"""Reference solution.

Claim before acting, and never retry a claim you cannot resolve.

The marker goes down *before* the transfer, so a restarted process can always
tell "I have already been here" from "I have not started". Finding that marker
means the previous process died somewhere around the transfer, and since the
legacy system cannot be queried, there is no way to learn whether the money
moved. Retrying would risk a second payout; the only honest move left is to
hand it to a person.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout

ATTEMPTING = "attempting"
COMPLETED = "completed"
NEEDS_REVIEW = "needs_review"


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    state_key = f"payout:{payout_id}:state"
    state = store.get(state_key)

    if state in (COMPLETED, NEEDS_REVIEW):
        return state

    if state == ATTEMPTING:
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    store.put(state_key, ATTEMPTING)
    try:
        legacy.transfer(amount_cents=amount_cents)
    except TransferTimeout:
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    store.put(state_key, COMPLETED)
    return COMPLETED
