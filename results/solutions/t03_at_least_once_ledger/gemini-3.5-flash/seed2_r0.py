import hashlib


def _token(message_id: str) -> str:
    """Generate a fixed-length string digest for a message_id to ensure
    durable store values remain well below the 32-byte limit."""
    return hashlib.blake2b(message_id.encode("utf-8"), digest_size=12).hexdigest()


def handle_message(message_id: str, amount_cents: int, store) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    if store.get(f"done:{message_id}") is not None:
        return

    msg_tok = _token(message_id)

    while True:
        if store.get(f"done:{message_id}") is not None:
            return

        state_str = store.get("state")
        if state_str is None:
            cur_bal = 0
            cur_seq = 0
        else:
            parts = state_str.split(":")
            cur_bal = int(parts[0])
            cur_seq = int(parts[1])

        # Check if a previous run allocated a sequence for this message
        prev_seq_str = store.get(f"att:{message_id}")
        if prev_seq_str is not None:
            prev_seq = int(prev_seq_str)
            if prev_seq <= cur_seq:
                owner_tok = store.get(f"seq:{prev_seq}")
                if owner_tok == msg_tok:
                    # Message won sequence prev_seq and balance was already committed
                    store.put(f"done:{message_id}", "1")
                    return

        next_seq = cur_seq + 1
        next_bal = cur_bal + amount_cents
        next_state_str = f"{next_bal}:{next_seq}"

        store.put(f"att:{message_id}", str(next_seq))
        store.put(f"seq:{next_seq}", msg_tok)

        if store.compare_and_set("state", state_str, next_state_str):
            store.put(f"done:{message_id}", "1")
            return


def read_balance(store) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    state_str = store.get("state")
    if state_str is None:
        return 0
    return int(state_str.split(":")[0])
