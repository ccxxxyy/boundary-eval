"""Known-correct, with the claim kept in its own key rather than as a third
value of the state key. Behaviourally identical, structurally different, so the
grader cannot be requiring one particular encoding of "in flight"."""

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
        # A previous process got as far as claiming. Whether the money moved is
        # unknowable from here.
        store.put(state_key, "needs_review")
        return "needs_review"

    store.put(claim_key, new_id())
    try:
        legacy.transfer(amount_cents=amount_cents)
    except TransferTimeout:
        store.put(state_key, "needs_review")
        return "needs_review"

    store.put(state_key, "completed")
    return "completed"
