from faultline.api import DurableStore

def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    state_key = f"msg:{message_id}"
    state = store.get(state_key)
    
    # If we have already fully processed this message, we can safely ignore it.
    if state == "applied":
        return

    # Read the current balance and the ID of the last message that updated it.
    bal_str = store.get("balance")
    if bal_str is None:
        current_bal = 0
        last_msg = None
    else:
        # Split on the first colon only, in case message_id contains colons.
        parts = bal_str.split(":", 1)
        current_bal = int(parts[0])
        last_msg = parts[1]

    # Cooperative recovery: check if the previous run crashed after updating the 
    # balance but before marking its message as "applied".
    if last_msg is not None:
        last_msg_state = store.get(f"msg:{last_msg}")
        if last_msg_state == "pending":
            # The balance includes last_msg's amount, but it wasn't marked applied.
            # We fix it now to ensure consistency.
            store.put(f"msg:{last_msg}", "applied")
            
            # If the message we are currently processing is exactly the one that 
            # was just recovered, its amount is already in the balance. We are done.
            if last_msg == message_id:
                return

    # Phase 1: Write intent to process this message.
    # If we crash after this, future runs (or other messages) will know we started.
    if state != "pending":
        store.put(state_key, "pending")

    # Phase 2: Atomically update the balance and record this message as the last applied.
    new_bal = current_bal + amount_cents
    store.put("balance", f"{new_bal}:{message_id}")
    
    # Phase 3: Mark this message as fully applied.
    store.put(state_key, "applied")


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    bal_str = store.get("balance")
    if bal_str is None:
        return 0
    parts = bal_str.split(":", 1)
    return int(parts[0])
