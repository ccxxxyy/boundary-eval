"""BROKEN. Expected violation: "looks lost".

Records "this message has been applied" and then applies it. The guard is in
the right place and the ordering looks conservative - mark first so you can
never double-count. A crash in the gap means the amount is never added and the
redelivery skips it, so the money quietly disappears.
"""

from __future__ import annotations

from faultline.api import DurableStore

BALANCE_KEY = "balance"


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    seen_key = f"seen:{message_id}"
    if store.get(seen_key) is not None:
        return

    store.put(seen_key, "yes")
    balance = int(store.get(BALANCE_KEY) or "0")
    store.put(BALANCE_KEY, str(balance + amount_cents))


def read_balance(store: DurableStore) -> int:
    return int(store.get(BALANCE_KEY) or "0")
