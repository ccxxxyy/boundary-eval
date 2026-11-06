from __future__ import annotations
from typing import Callable, Any


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: Any,
    legacy: Any,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
    state_key = f"payout:{payout_id}:state"

    state = store.get(state_key)

    if state == "completed":
        return "completed"
    if state == "needs_review":
        return "needs_review"

    # If state is "pending", a previous run initiated a transfer attempt.
    # To prevent duplicate payouts, flag for human review.
    if state == "pending":
        store.put(state_key, "needs_review")
        return "needs_review"

    # Claim the transfer attempt atomically.
    if not store.compare_and_set(state_key, None, "pending"):
        state = store.get(state_key)
        if state == "completed":
            return "completed"
        store.put(state_key, "needs_review")
        return "needs_review"

    try:
        legacy.transfer(amount_cents)
    except Exception:
        store.put(state_key, "needs_review")
        return "needs_review"

    store.put(state_key, "completed")
    return "completed"
