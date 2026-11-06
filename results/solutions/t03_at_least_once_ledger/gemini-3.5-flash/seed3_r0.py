from __future__ import annotations


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    msg_key = f"msg:{message_id}"
    status = store.get(msg_key)

    if status == "APPLIED":
        return

    if status is None:
        seq_str = store.get("tx_seq")
        tx_id = int(seq_str) if seq_str is not None else 1
        store.put("tx_seq", str(tx_id + 1))
        status = f"PENDING:{tx_id}"
        store.put(msg_key, status)

    tx_id = int(status.split(":")[1])

    while True:
        bal_str = store.get("balance")
        if bal_str is None:
            bal_cents = 0
            last_tx_id = 0
        else:
            parts = bal_str.split(":")
            bal_cents = int(parts[0])
            last_tx_id = int(parts[1])

        if last_tx_id == tx_id:
            break

        new_cents = bal_cents + amount_cents
        new_bal_str = f"{new_cents}:{tx_id}"

        if store.compare_and_set("balance", bal_str, new_bal_str):
            break

    store.put(msg_key, "APPLIED")


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    bal_str = store.get("balance")
    if bal_str is None:
        return 0
    return int(bal_str.split(":")[0])
