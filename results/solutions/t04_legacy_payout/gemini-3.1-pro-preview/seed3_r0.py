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
    attempt_key = f"payout:{payout_id}:attempted"

    # 1. If we already have a final state recorded, return it immediately.
    # This handles redeliveries where the previous run finished successfully
    # but the acknowledgement was lost.
    state = store.get(state_key)
    if state is not None:
        return state

    # 2. Atomically mark that we are attempting the transfer.
    # Since we have no idempotency key for the legacy API, we must ensure we
    # call it at most once. If this compare_and_set fails, it means a previous
    # run started the attempt but crashed before it could record a final state.
    # Because we cannot know if that previous run actually executed the transfer
    # before crashing, we must flag it for manual review.
    if not store.compare_and_set(attempt_key, None, "yes"):
        store.put(state_key, "needs_review")
        return "needs_review"

    # 3. Execute the transfer.
    # If it times out, or fails for any other reason, the outcome is unknown.
    # We catch Exception to ensure no errors escape, as required.
    try:
        legacy.transfer(amount_cents)
    except Exception:
        store.put(state_key, "needs_review")
        return "needs_review"

    # 4. The transfer succeeded. Record and return completion.
    store.put(state_key, "completed")
    return "completed"
