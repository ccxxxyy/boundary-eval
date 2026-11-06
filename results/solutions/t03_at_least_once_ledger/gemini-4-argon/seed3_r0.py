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
_DONE_PREFIX = "d:"


def _token(message_id: str) -> str:
    """Return a deterministic token for `message_id` of at most 15 UTF-8 bytes
    that never contains a newline."""
    raw = message_id.encode("utf-8")
    if len(raw) <= 15 and b"\n" not in raw and not raw.startswith(b"\t"):
        return message_id
    digest = hashlib.sha256(raw).digest()[:11]
    return "\t" + base64.b85encode(digest).decode("ascii")


def _format_bal(balance: int, tok: str) -> str:
    return f"{balance:x}\n{tok}"


def _parse_bal(raw: str) -> tuple[int, str]:
    bal_hex, tok = raw.split("\n", 1)
    return int(bal_hex, 16), tok


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    tok = _token(message_id)
    raw_bal = store.get(_BAL_KEY)

    if raw_bal is None:
        balance = 0
        last_tok: str | None = None
    else:
        balance, last_tok = _parse_bal(raw_bal)

    # The set of already-applied messages is `{last_tok} | {t : d:t in store}`.
    if tok == last_tok or store.get(_DONE_PREFIX + tok) is not None:
        return

    # Persist `last_tok` in the done-set before overwriting `_BAL_KEY` so the
    # set of applied messages and the balance transition atomically together
    # on the subsequent `_BAL_KEY` write.
    if last_tok is not None and store.get(_DONE_PREFIX + last_tok) is None:
        store.put(_DONE_PREFIX + last_tok, "1")

    new_balance = balance + amount_cents
    store.put(_BAL_KEY, _format_bal(new_balance, tok))


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
    raw_bal = store.get(_BAL_KEY)
    if raw_bal is None:
        return 0
    balance, _ = _parse_bal(raw_bal)
    return balance
