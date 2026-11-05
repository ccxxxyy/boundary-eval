"""Fill in `handle_order`. See prompt.md for the contract."""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, GatewayTimeout, PaymentGateway


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    raise NotImplementedError
