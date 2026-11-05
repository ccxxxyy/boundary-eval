"""Reference solution.

The balance and the set of messages already folded into it live in one key, so
one `compare_and_set` makes both facts durable together. Either the message is
applied and recorded, or neither happened and the redelivery will apply it.
There is no window in between because there is only one write.
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


def _encode(balance: int, applied: list[str]) -> str:
    return json.dumps({"balance": balance, "applied": applied}, sort_keys=True)


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    while True:
        raw = store.get(STATE_KEY)
        balance, applied = _decode(raw)
        if message_id in applied:
            return
        candidate = _encode(balance + amount_cents, sorted([*applied, message_id]))
        if store.compare_and_set(STATE_KEY, raw, candidate):
            return


def read_balance(store: DurableStore) -> int:
    balance, _ = _decode(store.get(STATE_KEY))
    return balance
