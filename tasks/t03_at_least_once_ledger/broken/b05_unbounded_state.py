"""BROKEN. Expected violation: "StoreValueTooLarge".

The textbook answer, and the one a model reaches for first: serialise the
balance and every message id ever applied into a single key, then make the
whole thing durable with one compare-and-set. It really is crash-safe - that
is why it is so appealing - but only because it turns a single-key store into
a transactional one by never using a second key.

It is also a genuine production bug. The value grows with every distinct
message the consumer has ever seen, so the row grows without bound. The store
caps one value, the prompt says so, and this solution walks straight past the
cap.
"""

from __future__ import annotations

import json

from faultline.api import DurableStore

STATE_KEY = "ledger:state"


def _decode(raw: str | None) -> tuple[int, list[str]]:
    if raw is None:
        return 0, []
    state = json.loads(raw)
    return int(state["balance"]), list(state["applied"])


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    while True:
        raw = store.get(STATE_KEY)
        balance, applied = _decode(raw)
        if message_id in applied:
            return
        candidate = json.dumps(
            {"balance": balance + amount_cents, "applied": sorted([*applied, message_id])},
            sort_keys=True,
        )
        if store.compare_and_set(STATE_KEY, raw, candidate):
            return


def read_balance(store: DurableStore) -> int:
    balance, _ = _decode(store.get(STATE_KEY))
    return balance
