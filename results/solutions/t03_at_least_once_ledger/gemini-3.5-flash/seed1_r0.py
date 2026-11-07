import hashlib
from faultline.api import DurableStore, StoreValueTooLarge


def _get_token(message_id: str) -> str:
    """Generate a deterministic 10-hex-character token for a message_id."""
    return hashlib.md5(message_id.encode("utf-8")).hexdigest()[:10]


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    msg_key = f"msg:{message_id}"
    token = _get_token(message_id)

    # Step 1: Ensure message state is marked PENDING (or return if already DONE)
    while True:
        status = store.get(msg_key)
        if status == "DONE":
            return
        if status == "PENDING":
            break
        if store.compare_and_set(msg_key, None, "PENDING"):
            break

    # Step 2: Apply balance update atomically
    while True:
        bal_val = store.get("balance")
        if bal_val is None:
            current_cents = 0
            current_token = ""
        else:
            cents_str, current_token = bal_val.split(":", 1)
            current_cents = int(cents_str)

        if current_token == token:
            break

        new_cents = current_cents + amount_cents
        new_bal_val = f"{new_cents}:{token}"

        if store.compare_and_set("balance", bal_val, new_bal_val):
            break

    # Step 3: Mark message as DONE
    store.put(msg_key, "DONE")


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    bal_val = store.get("balance")
    if bal_val is None:
        return 0
    cents_str, _ = bal_val.split(":", 1)
    return int(cents_str)
