from __future__ import annotations

import base64
import hashlib
from typing import Protocol


class DurableStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


_BAL_KEY = "bal"


def _make_tag(message_id: str) -> str:
    raw = message_id.encode("utf-8")
    if (
        message_id
        and len(raw) <= 15
        and message_id.isascii()
        and message_id.isprintable()
        and " " not in message_id
        and not message_id.startswith("#")
    ):
        return message_id
    digest = hashlib.blake2b(raw, digest_size=10).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return "#" + encoded


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    tag = _make_tag(message_id)
    done_key = f"m:{tag}"

    if store.get(done_key) is not None:
        return

    bal_val = store.get(_BAL_KEY)
    if bal_val is None:
        bal = 0
    else:
        bal_str, last_tag = bal_val.split(" ", 1)
        if last_tag == tag:
            store.put(done_key, "1")
            return
        last_done_key = f"m:{last_tag}"
        if store.get(last_done_key) is None:
            store.put(last_done_key, "1")
        bal = int(bal_str, 16)

    new_bal = bal + amount_cents
    store.put(_BAL_KEY, f"{new_bal:x} {tag}")
    store.put(done_key, "1")


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    bal_val = store.get(_BAL_KEY)
    if bal_val is None:
        return 0
    bal_str, _ = bal_val.split(" ", 1)
    return int(bal_str, 16)
