from __future__ import annotations

def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    
    # 1. Recover any pending state from a previous crash.
    # If the balance key contains a colon, it means a process crashed after
    # updating the balance but potentially before marking the message as done.
    val = store.get("balance")
    if val and ":" in val:
        bal_str, pending_msg = val.split(":", 1)
        # Ensure the pending message is marked as done so it isn't reapplied.
        store.put("msg:" + pending_msg, "done")
        # Clean up the balance key to just hold the integer balance.
        store.compare_and_set("balance", val, bal_str)
        current_bal = int(bal_str)
    else:
        current_bal = int(val) if val else 0

    # 2. Check if the current message has already been processed.
    if store.get("msg:" + message_id) == "done":
        return

    # 3. Calculate the new balance.
    new_bal = current_bal + amount_cents
    
    # 4. Write the new balance and the message ID together.
    # This acts as an atomic commit: once this succeeds, the balance is updated
    # and we have a durable record of which message caused the update.
    new_val = f"{new_bal}:{message_id}"
    store.put("balance", new_val)
    
    # 5. Mark the message as done in its own key.
    store.put("msg:" + message_id, "done")
    
    # 6. Clean up the balance key to just the balance.
    # If we crash before this, step 1 will handle the cleanup on redelivery.
    store.compare_and_set("balance", new_val, str(new_bal))


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    val = store.get("balance")
    if not val:
        return 0
    
    # If there's a colon, a crash happened mid-update, but the balance part 
    # (before the colon) is already the correct, updated balance.
    if ":" in val:
        return int(val.split(":", 1)[0])
        
    return int(val)
