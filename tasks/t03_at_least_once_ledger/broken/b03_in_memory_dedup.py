"""BROKEN. Expected violation: "one time too many".

Deduplicates in a module-level set, which handles the duplicates inside a
single batch perfectly and therefore passes any test that does not restart the
process. The set is empty again after a crash, so the redelivered batch is
applied on top of the work that already survived.
"""

from __future__ import annotations

from faultline.api import DurableStore

BALANCE_KEY = "balance"
_SEEN: set[str] = set()


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    if message_id in _SEEN:
        return
    _SEEN.add(message_id)
    balance = int(store.get(BALANCE_KEY) or "0")
    store.put(BALANCE_KEY, str(balance + amount_cents))


def read_balance(store: DurableStore) -> int:
    return int(store.get(BALANCE_KEY) or "0")
