from __future__ import annotations

def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    status_key = f"s:{message_id}"
    
    while True:
        # 1. Check if we have already fully processed this message.
        status = store.get(status_key)
        if status == "done":
            return
            
        # 2. Mark our intent to process this message.
        if status is None:
            if not store.compare_and_set(status_key, None, "pending"):
                continue  # State changed, retry
            status = "pending"
            
        if status == "pending":
            # 3. Read the current balance and the ID of the last message that updated it.
            val = store.get("balance")
            if val is None:
                # Initialize the balance if it doesn't exist.
                # "0" (without a colon) represents the pristine initial state.
                store.compare_and_set("balance", None, "0")
                continue
                
            if ":" in val:
                parts = val.split(":", 1)
                current_bal = int(parts[0])
                last_id = parts[1]
            else:
                current_bal = int(val)
                last_id = None
                
            # 4. If we are the last message to update the balance, we already succeeded
            # in a previous run but crashed before marking ourselves as "done".
            if last_id is not None and last_id == message_id:
                store.compare_and_set(status_key, "pending", "done")
                return
                
            # 5. If the previous message crashed before marking itself as "done",
            # we must help it finish. Otherwise, when it is redelivered, it won't
            # see its ID in the balance and will double-count its amount.
            if last_id is not None:
                last_status = store.get(f"s:{last_id}")
                if last_status == "pending":
                    store.compare_and_set(f"s:{last_id}", "pending", "done")
                    
            # 6. Calculate the new balance and format it with our message ID.
            # The prompt guarantees this combined string will fit within the 32-byte limit.
            new_bal = current_bal + amount_cents
            new_val = f"{new_bal}:{message_id}"
            
            # 7. Atomically swing the balance to the new value.
            if store.compare_and_set("balance", val, new_val):
                # Success! We can now mark ourselves as done.
                store.compare_and_set(status_key, "pending", "done")
                return
            else:
                # The balance was updated by someone else (or a previous run), retry.
                continue


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    val = store.get("balance")
    if val is None:
        return 0
        
    if ":" in val:
        return int(val.split(":", 1)[0])
        
    return int(val)
