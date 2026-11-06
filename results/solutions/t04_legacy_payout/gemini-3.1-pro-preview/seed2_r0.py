from typing import Callable

class DurableStore:
    """A durable key-value store."""
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...
    def delete(self, key: str) -> None: ...

class LegacyTransferAPI:
    def transfer(self, amount_cents: int) -> str: ...

class TransferTimeout(Exception):
    """The legacy system did not answer."""

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
            
        if state == "intent":
            # We crashed during a previous attempt, or timed out and crashed before
            # recording the outcome. We cannot know if the transfer actually happened,
            # so we must flag it for manual review to avoid a double payout.
            store.put(state_key, "needs_review")
            return "needs_review"
            
        if state is None:
            # Record our intent to transfer before making the remote call.
            # If we crash immediately after this takes effect, the next run will
            # see "intent" and safely transition to "needs_review".
            if store.compare_and_set(state_key, None, "intent"):
                try:
                    legacy.transfer(amount_cents)
                except Exception:
                    # If it times out (TransferTimeout) or raises any other exception,
                    # the outcome is unknown. We must flag it for review.
                    store.put(state_key, "needs_review")
                    return "needs_review"
                
                # The transfer succeeded and we know it happened exactly once.
                store.put(state_key, "completed")
                return "completed"
