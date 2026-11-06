def send_payout(
    payout_id: str,
    amount_cents: int,
    store,
    legacy,
    new_id,
) -> str:
    """Pay out `amount_cents` at most once.

    Return "completed" if the money has moved exactly once and that fact is
    durably recorded. Return "needs_review" if the outcome is unknown or
    cannot be completed safely, so a person can reconcile it.
    """
    state_key = f"payout:{payout_id}:state"
    worker_key = f"payout:{payout_id}:worker"
    
    # 1. If we already have a definitive state, return it immediately.
    state = store.get(state_key)
    if state is not None:
        return state
        
    # 2. Attempt to become the exclusive worker for this payout.
    worker_id = new_id()
    if store.compare_and_set(worker_key, None, worker_id):
        # We won the lock. We are the only worker that will ever attempt the transfer.
        try:
            legacy.transfer(amount_cents)
        except Exception:
            # The transfer timed out. We don't know if the money moved or not.
            # We must mark it for review.
            store.put(state_key, "needs_review")
            return "needs_review"
            
        # The transfer succeeded normally. The money moved exactly once.
        store.put(state_key, "completed")
        return "completed"
    else:
        # Another worker is already handling this payout.
        # Because we cannot know if the other worker died before transferring,
        # died during the transfer, or is just running slowly, it is unsafe to retry.
        # We mark the state as "needs_review" ONLY IF it hasn't been completed yet.
        store.compare_and_set(state_key, None, "needs_review")
        
        # Return whatever the state ended up being ("completed" if the other worker 
        # succeeded in the meantime, or "needs_review" otherwise).
        final_state = store.get(state_key)
        return final_state if final_state is not None else "needs_review"
