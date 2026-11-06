from __future__ import annotations

import base64
import hashlib
from typing import Protocol


class DurableStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...
    def delete(self, key: str) -> None: ...


_BALANCE_KEY = "bal"


def _make_tag(message_id: str) -> str:
    """Return a deterministic identifier for `message_id` of at most 16 UTF-8 bytes."""
    raw = message_id.encode("utf-8")
    if not message_id.startswith("\t") and len(raw) <= 15:
        return message_id
    digest = hashlib.sha256(raw).digest()[:12]
    return "\t" + base64.b85encode(digest).decode("ascii")


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    tag = _make_tag(message_id)

    state = store.get(_BALANCE_KEY)
    if state is not None:
        bal_str, last_tag = state.split(":", 1)
        balance = int(bal_str)
        if last_tag == tag:
            return
    else:
        balance = 0
        last_tag = None

    if store.get(f"d:{tag}") is not None:
        return

    if last_tag is not None:
        store.put(f"d:{last_tag}", "1")

    new_balance = balance + amount_cents
    store.put(_BALANCE_KEY, f"{new_balance}:{tag}")


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    state = store.get(_BALANCE_KEY)
    if state is None:
        return 0
    bal_str, _ = state.split(":", 1)
    return int(bal_str)
