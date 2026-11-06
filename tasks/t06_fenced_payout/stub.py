"""Fill in `send_payout`. See prompt.md for the contract."""

from __future__ import annotations

from faultline.api import DurableStore, LegacyTransferAPI


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id,
) -> str:
    """Pay out `amount_cents` at most once. Return "completed" or
    "needs_review"."""
    raise NotImplementedError
