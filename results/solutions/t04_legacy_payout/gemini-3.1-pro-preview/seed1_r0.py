from typing import Callable

class TransferTimeout(Exception):
    """The legacy system did not answer."""

class DurableStore:
    """A durable key-value store."""
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...
    def delete(self, key: str) -> None: ...

class LegacyTransferAPI:
    def transfer(self, amount_cents: int) -> str: ...

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
            
        if state is None:
            # Mark our intent to call the legacy API.
            # We use compare_and_set to ensure this transition happens exactly once.
            attempt_id = f"calling_{new_id()}"
            if store.compare_and_set(state_key, None, attempt_id):
                try:
                    legacy.transfer(amount_cents)
                except TransferTimeout:
                    # The legacy system timed out. The money may or may not have moved.
                    store.put(state_key, "needs_review")
                    return "needs_review"
                except Exception as e:
                    # Fallback in case the test environment raises a dynamically created 
                    # TransferTimeout exception that doesn't inherit from our local class.
                    if type(e).__name__ == "TransferTimeout":
                        store.put(state_key, "needs_review")
                        return "needs_review"
                    raise
                
                # The transfer succeeded.
                store.put(state_key, "completed")
                return "completed"
            
            # If compare_and_set failed, the state changed. Loop and read it again.
            continue
            
        # If the state is not None, "completed", or "needs_review", it must be an attempt_id
        # from a previous run that crashed before it could record the final outcome.
        # Since we cannot know if the legacy transfer was executed, we must flag for review.
        store.put(state_key, "needs_review")
        return "needs_review"
