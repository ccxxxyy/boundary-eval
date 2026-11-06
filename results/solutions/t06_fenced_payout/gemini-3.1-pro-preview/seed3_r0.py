def send_payout(
    payout_id: str,
    amount_cents: int,
    store: "DurableStore",
    legacy: "LegacyTransferAPI",
    new_id,
) -> str:
    state_key = f"payout:{payout_id}:state"
    worker_id = new_id()
    
    while True:
        state = store.get(state_key)
        
        if state == "completed":
            return "completed"
            
        if state == "needs_review":
            return "needs_review"
            
        if state is not None and state.startswith("started:"):
            # Another worker started this, or we crashed after starting.
            # We don't know if they called transfer(), so we must escalate.
            if store.compare_and_set(state_key, state, "needs_review"):
                return "needs_review"
            # If CAS fails, the state changed. Loop and read the new state.
            continue
            
        if state is None:
            # Try to exclusively claim the right to execute the transfer.
            if store.compare_and_set(state_key, None, f"started:{worker_id}"):
                break
            # If CAS fails, another worker claimed it first. Loop and read.
            continue

    # We have exclusively claimed the right to transfer. No other worker
    # will ever reach this point for this payout_id.
    try:
        legacy.transfer(amount_cents)
    except Exception:
        # We catch Exception to safely handle TransferTimeout.
        # The transfer may or may not have happened.
        store.put(state_key, "needs_review")
        return "needs_review"

    # The transfer succeeded. We know for a fact the money moved exactly once.
    # Even if another worker took over while we were transferring and set the 
    # state to "needs_review", it is safe and correct to overwrite it with 
    # "completed" because we have the definitive successful outcome.
    store.put(state_key, "completed")
    return "completed"
