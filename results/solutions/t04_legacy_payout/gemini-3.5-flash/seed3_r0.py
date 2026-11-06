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

    current_state = store.get(state_key)
    if current_state == "completed":
        return "completed"
    if current_state == "needs_review":
        return "needs_review"
    if current_state is not None:
        store.put(state_key, "needs_review")
        return "needs_review"

    # Pessimistically transition state to "needs_review" before calling legacy API.
    # If the process crashes after this CAS, redeliveries will see "needs_review"
    # and will not attempt legacy.transfer again, guaranteeing at most one transfer.
    if not store.compare_and_set(state_key, None, "needs_review"):
        current_state = store.get(state_key)
        if current_state == "completed":
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
