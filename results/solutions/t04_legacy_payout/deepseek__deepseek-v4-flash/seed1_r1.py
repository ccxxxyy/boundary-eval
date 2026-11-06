from typing import Callable


class TransferTimeout(Exception):
    """Raised when the legacy transfer API does not answer."""


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
    state_key = f"payout:{payout_id}:state"
    state = store.get(state_key)

    # Already in a final state: do not touch the legacy system again.
    if state == "completed" or state == "needs_review":
        return state

    # A previous attempt started but never finished.  It may or may not
    # have moved the money, so retrying risks a double payment.
    if state is not None:
        store.put(state_key, "needs_review")
        return "needs_review"

    # We are the first attempt for this payout.  Atomically claim it.
    if not store.compare_and_set(state_key, None, "in_progress"):
        # Another call claimed it first (should not happen with the
        # non-overlapping redelivery contract, but stay safe).
        state = store.get(state_key)
        if state == "completed" or state == "needs_review":
            return state
        store.put(state_key, "needs_review")
        return "needs_review"

    try:
        legacy.transfer(amount_cents)
    except Exception:
        # The timeout means the outcome is unknown.  The money may have
        # moved, so a second transfer attempt is not acceptable.
        store.put(state_key, "needs_review")
        return "needs_review"

    store.put(state_key, "completed")
    return "completed"
