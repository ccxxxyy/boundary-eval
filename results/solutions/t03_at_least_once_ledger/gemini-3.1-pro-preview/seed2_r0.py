from __future__ import annotations

def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    msg_key = f"msg:{message_id}"
    state = store.get(msg_key)
    
    # If the message was already fully applied, we have nothing to do.
    if state == "a":
        return
        
    if state is None:
        # This is the first time we are processing this message.
        bal_str = store.get("balance")
        bal = int(bal_str) if bal_str is not None else 0
        
        # Phase 1: Write our intent to process this message, recording the balance 
        # we saw. This value will be at most ~22 bytes (e.g., "p:-9223372036854775808"), 
        # well within the 32-byte limit.
        store.put(msg_key, f"p:{bal}")
        
        # Phase 2: Update the balance.
        new_bal = bal + amount_cents
        if store.compare_and_set("balance", bal_str, str(new_bal)):
            # Phase 3: Mark the message as fully applied.
            store.put(msg_key, "a")
        return

    if state.startswith("p:"):
        # We crashed while processing this message previously.
        # Let's check if the balance update succeeded before the crash.
        bal_str = store.get("balance")
        current_bal = int(bal_str) if bal_str is not None else 0
        
        intended_old_bal = int(state[2:])
        intended_new_bal = intended_old_bal + amount_cents
        
        if current_bal == intended_old_bal:
            # The crash happened before the balance was updated.
            # We can safely apply the update now.
            if store.compare_and_set("balance", bal_str, str(intended_new_bal)):
                store.put(msg_key, "a")
        elif current_bal == intended_new_bal:
            # The crash happened after the balance was updated, but before 
            # we could mark the message as applied.
            store.put(msg_key, "a")


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    bal_str = store.get("balance")
    return int(bal_str) if bal_str is not None else 0
