"""Fill in both functions. See prompt.md for the contract."""

from __future__ import annotations

from faultline.api import DurableStore


def handle_transfer(
    transfer_id: str,
    source: str,
    target: str,
    amount_cents: int,
    store: DurableStore,
) -> str:
    """Move `amount_cents` from `source` to `target`, at most once.
    Return "applied" or "rejected"."""
    raise NotImplementedError


def read_balance(account: str, store: DurableStore) -> int:
    """Return `account`'s balance in cents, from durable state alone."""
    raise NotImplementedError
