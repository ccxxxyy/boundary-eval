from typing import Protocol


class DurableStore(Protocol):
    """A durable key-value store.

    Each operation is atomic, and once it returns, its effect is durable: it
    survives a process crash. The four methods below are the whole API.
    """

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


def _recover(store: DurableStore) -> None:
    """Finish any interrupted balance update from a previous process crash."""
    wip_id = store.get("wip_id")
    if wip_id is not None:
        wip_val = store.get("wip_val")
        # If wip_id is set, wip_val must have been set before it.
        if wip_val is not None:
            store.put("balance", wip_val)
            store.put(f"applied:{wip_id}", "true")
        # Clear the intent markers.
        store.delete("wip_id")
        store.delete("wip_val")


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    # 1. Ensure any previous interrupted work is completed.
    _recover(store)

    # 2. Check if this message has already been fully applied.
    if store.get(f"applied:{message_id}") is not None:
        return

    # 3. Calculate the new state.
    bal_str = store.get("balance")
    current_bal = int(bal_str) if bal_str is not None else 0
    target_bal = current_bal + amount_cents

    # 4. Record the intent to update (Write-Ahead Log pattern).
    # We set the value first, then the ID. If we crash after setting the value
    # but before the ID, the next run will ignore the value.
    store.put("wip_val", str(target_bal))
    store.put("wip_id", message_id)

    # 5. Apply the intent.
    store.put("balance", str(target_bal))
    store.put(f"applied:{message_id}", "true")

    # 6. Clean up the intent markers.
    store.delete("wip_id")
    store.delete("wip_val")


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    # If a message is currently in the "committed" state (wip_id is set),
    # its target balance is the true current balance.
    wip_id = store.get("wip_id")
    if wip_id is not None:
        wip_val = store.get("wip_val")
        if wip_val is not None:
            return int(wip_val)

    # Otherwise, the balance key is the source of truth.
    bal_str = store.get("balance")
    if bal_str is not None:
        return int(bal_str)

    return 0
