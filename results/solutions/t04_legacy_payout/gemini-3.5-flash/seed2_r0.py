from __future__ import annotations
from typing import Callable


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
    state_key = f"payout:{payout_id}:state"
    attempt_key = f"payout:{payout_id}:attempt"

    # 1. Return early if state was already recorded in a previous run
    current_state = store.get(state_key)
    if current_state is not None:
        return current_state

    # 2. Record intent to execute the transfer before calling legacy API.
    # compare_and_set guarantees that at most one attempt can ever be claimed.
    attempt_token = new_id()
    if not store.compare_and_set(attempt_key, None, attempt_token):
        # A previous run already claimed the attempt key.
        current_state = store.get(state_key)
        if current_state is not None:
            return current_state

        # An attempt was made by a crashed run, but final state was not recorded.
        # To avoid moving money twice, flag for manual review.
        store.put(state_key, "needs_review")
        return "needs_review"

    # 3. Attempt the legacy transfer exactly once
    try:
        legacy.transfer(amount_cents)
    except Exception:
        store.put(state_key, "needs_review")
        return "needs_review"

    # 4. Transfer succeeded
    store.put(state_key, "completed")
    return "completed"
