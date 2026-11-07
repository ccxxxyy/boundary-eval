from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout

def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id,
) -> str:
    """Pay out `amount_cents` at most once.

    Return "completed" if the money has moved exactly once and that fact is
    durably recorded. Return "needs_review" if the outcome is unknown or
    cannot be completed safely, so a person can reconcile it.
    """
    payout_key = f"payout:{payout_id}:state"
    
    while True:
        state = store.get(payout_key)
        
        if state == "completed":
            return "completed"
            
        if state == "needs_review":
            return "needs_review"
            
        if state == "transferring":
            # Another worker is currently transferring, or crashed while transferring.
            # We cannot know if the transfer succeeded, failed, or is still ongoing.
            # We must transition to needs_review to prevent any future worker from retrying.
            if store.compare_and_set(payout_key, "transferring", "needs_review"):
                return "needs_review"
            # If CAS failed, the state changed. Loop and re-evaluate.
            continue
            
        if state is None:
            # Try to claim the transfer operation.
            if store.compare_and_set(payout_key, None, "transferring"):
                try:
                    legacy.transfer(amount_cents)
                except TransferTimeout:
                    # The transfer may or may not have happened.
                    # Record needs_review so a human can reconcile.
                    store.put(payout_key, "needs_review")
                    return "needs_review"
                
                # The transfer definitely succeeded.
                # Overwrite any pessimistic needs_review set by concurrent workers
                # because we definitively know the transfer was successful.
                store.put(payout_key, "completed")
                return "completed"
            # If CAS failed, another worker claimed it. Loop and re-evaluate.
            continue
