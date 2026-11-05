"""BROKEN. Expected violation: "one time too many".

The other obvious ordering: apply the amount, then record that you did. A
crash in the gap means the redelivery sees an unmarked message and applies it
a second time. Reordering the two writes cannot fix this task - that is the
point of it.
"""

from __future__ import annotations

from faultline.api import DurableStore

BALANCE_KEY = "balance"


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    seen_key = f"seen:{message_id}"
    if store.get(seen_key) is not None:
        return

    balance = int(store.get(BALANCE_KEY) or "0")
    store.put(BALANCE_KEY, str(balance + amount_cents))
    store.put(seen_key, "yes")


def read_balance(store: DurableStore) -> int:
    return int(store.get(BALANCE_KEY) or "0")
