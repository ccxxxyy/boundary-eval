from typing import Callable
from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
    state_key = f"payout:{payout_id}:state"

    while True:
        state = store.get(state_key)

        if state == "completed":
            return "completed"

        if state == "needs_review":
            return "needs_review"

        if state == "attempting":
            # A previous run started the transfer but we don't know whether it
            # actually executed. We must never retry; hand off to a human.
            store.put(state_key, "needs_review")
            return "needs_review"

        if state is None:
            # Claim the one and only transfer attempt.
            if not store.compare_and_set(state_key, None, "attempting"):
                # State changed underneath us; re-read and handle.
                continue

            try:
                legacy.transfer(amount_cents)
            except Exception:
                # Timeout or any other failure: outcome is unknown.
                store.put(state_key, "needs_review")
                return "needs_review"
            else:
                # The transfer definitely happened exactly once.
                store.put(state_key, "completed")
                return "completed"

        # Unexpected state value. Be conservative.
        store.put(state_key, "needs_review")
        return "needs_review"
