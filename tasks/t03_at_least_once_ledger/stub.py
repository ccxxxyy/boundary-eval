"""Fill in both functions. See prompt.md for the contract."""

from __future__ import annotations

from faultline.api import DurableStore


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    raise NotImplementedError


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from durable state alone."""
    raise NotImplementedError
