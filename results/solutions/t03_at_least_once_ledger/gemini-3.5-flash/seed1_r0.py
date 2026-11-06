import hashlib


def _token(message_id: str) -> str:
    return hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:10]


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    if store.get(f"applied:{message_id}") is not None:
        return

    m_token = _token(message_id)

    if store.get(f"win_msg:{m_token}") is not None:
        store.put(f"applied:{message_id}", "1")
        return

    while True:
        if store.get(f"applied:{message_id}") is not None:
            return
        if store.get(f"win_msg:{m_token}") is not None:
            store.put(f"applied:{message_id}", "1")
            return

        head_str = store.get("head")
        if head_str is None:
            curr_bal = 0
            curr_token = ""
        else:
            parts = head_str.split(":")
            curr_bal = int(parts[0])
            curr_token = parts[1]

        if curr_token == m_token:
            store.put(f"win_msg:{m_token}", "1")
            store.put(f"applied:{message_id}", "1")
            return

        if curr_token:
            store.put(f"win_msg:{curr_token}", "1")

        new_bal = curr_bal + amount_cents
        new_head_str = f"{new_bal}:{m_token}"

        if store.compare_and_set("head", head_str, new_head_str):
            store.put(f"win_msg:{m_token}", "1")
            store.put(f"applied:{message_id}", "1")
            return


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    head_str = store.get("head")
    if head_str is None:
        return 0
    return int(head_str.split(":")[0])
