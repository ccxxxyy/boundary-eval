"""BROKEN. Expected violation: "expected 178000".

No deduplication whatsoever. Included as the floor of the task: it is caught by
the very first self-check scenario, so it measures nothing on its own, but its
presence proves the invariant check is wired up and reacting to the obvious
case as well as the subtle ones.
"""

from __future__ import annotations

from faultline.api import DurableStore

BALANCE_KEY = "balance"


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    balance = int(store.get(BALANCE_KEY) or "0")
    store.put(BALANCE_KEY, str(balance + amount_cents))


def read_balance(store: DurableStore) -> int:
    return int(store.get(BALANCE_KEY) or "0")
