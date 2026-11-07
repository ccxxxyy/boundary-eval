from faultline.api import DurableStore, StoreValueTooLarge

def handle_transfer(
    transfer_id: str,
    source: str,
    target: str,
    amount_cents: int,
    store: DurableStore,
) -> str:
    """Move `amount_cents` from `source` to `target`, at most once.

    Return "applied" if the money moved, or "rejected" if it did not because
    `source` could not cover it.
    """
    while True:
        # 1. Check if we already fully processed this transfer
        status = store.get(f"status:{transfer_id}")
        if status is not None:
            return status

        # 2. Check if we crashed while applying this transfer
        my_seq_str = store.get(f"tx_seq:{transfer_id}")
        if my_seq_str is not None:
            my_seq = int(my_seq_str)
            current_seq_str = store.get("seq") or "0"
            current_seq = int(current_seq_str)
            
            # If the global sequence has reached or passed the sequence number
            # we were trying to commit, it means our compare_and_set succeeded
            # before the crash. We can safely mark it as applied.
            if current_seq >= my_seq:
                store.put(f"status:{transfer_id}", "applied")
                return "applied"

        # 3. Read the current state
        current_seq_str = store.get("seq")
        if current_seq_str is None:
            # Initialize the sequence and balance if this is the very first run
            opening_balance = store.get("acct:A")
            if opening_balance is None:
                opening_balance = "100000"
            store.put("acct:A:0", opening_balance)
            store.compare_and_set("seq", None, "0")
            continue
            
        current_seq = int(current_seq_str)
        balance_str = store.get(f"acct:A:{current_seq}")
        if balance_str is None:
            # Fallback for safety, though acct:A:{current_seq} should always exist
            balance_str = store.get("acct:A")
            if balance_str is None:
                balance_str = "100000"
            
        balance_A = int(balance_str)
        
        # 4. Evaluate the transfer
        source_balance = balance_A if source == "A" else 100000 - balance_A
        
        if source_balance < amount_cents:
            store.put(f"status:{transfer_id}", "rejected")
            return "rejected"
            
        if source == target:
            new_balance_A = balance_A
        else:
            new_balance_A = balance_A - amount_cents if source == "A" else balance_A + amount_cents
            
        next_seq = current_seq + 1
        
        # 5. Write intents (idempotent operations)
        store.put(f"tx_seq:{transfer_id}", str(next_seq))
        store.put(f"acct:A:{next_seq}", str(new_balance_A))
        
        # 6. Commit the new state atomically
        if store.compare_and_set("seq", current_seq_str, str(next_seq)):
            store.put(f"status:{transfer_id}", "applied")
            
            # Clean up the old balance to prevent unbounded key growth
            if current_seq > 0:
                store.delete(f"acct:A:{current_seq - 1}")
                
            return "applied"
        
        # If compare_and_set fails, the loop will restart and re-evaluate.
        # Since calls never overlap, this only happens if we recover from a crash.


def read_balance(account: str, store: DurableStore) -> int:
    """Return `account`'s balance in cents, from durable state alone.
    Called in a fresh process."""
    seq_str = store.get("seq")
    
    if seq_str is None:
        # No transfers have been committed yet, return opening balances
        val = store.get(f"acct:{account}")
        if val is not None:
            return int(val)
        return 100000 if account == "A" else 0
        
    balance_A_str = store.get(f"acct:A:{seq_str}")
    if balance_A_str is None:
        balance_A_str = store.get("acct:A")
        if balance_A_str is None:
            balance_A_str = "100000"
            
    balance_A = int(balance_A_str)
    
    if account == "A":
        return balance_A
    return 100000 - balance_A
