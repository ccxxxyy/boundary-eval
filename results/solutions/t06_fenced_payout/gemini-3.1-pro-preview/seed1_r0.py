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
    worker_key = f"payout:{payout_id}:worker"
    state_key = f"payout:{payout_id}:state"
    
    wid = new_id()
    
    # Try to become the designated worker for this payout.
    # Since `wid` is unique per run and `compare_and_set` is atomic, 
    # exactly one worker will ever acquire this lock.
    if store.compare_and_set(worker_key, None, wid):
        try:
            legacy.transfer(amount_cents)
        except Exception:
            # If transfer times out or fails, we don't know the outcome.
            # We must escalate for review.
            store.put(state_key, "needs_review")
            return "needs_review"
            
        # Transfer succeeded, money moved exactly once.
        store.put(state_key, "completed")
        return "completed"
    else:
        # Another worker is handling or has handled this payout.
        # We cannot safely retry the transfer because the original worker 
        # might have already moved the money or might still be running.
        state = store.get(state_key)
        if state == "completed":
            return "completed"
            
        if state != "needs_review":
            # Mark as needs_review since the original worker might be dead.
            # We use compare_and_set to avoid overwriting a "completed" state
            # in case the original worker just finished successfully.
            if not store.compare_and_set(state_key, state, "needs_review"):
                # The state changed while we were trying to update it.
                # Fetch the latest state to see if the original worker finished.
                state = store.get(state_key)
            else:
                state = "needs_review"
                
        if state == "completed":
            return "completed"
            
        return "needs_review"
