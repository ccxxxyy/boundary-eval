"""BROKEN. Expected violation: "the handler raised GatewayTimeout".

Key handling is correct; the documented timeout is simply never caught. The
charge may well have succeeded, but the worker reports a failure.
"""

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
    slot = f"idem:{order_id}"
    key = store.get(slot)
    if key is None:
        key = new_id()
        store.put(slot, key)
    return gateway.charge(idempotency_key=key, amount_cents=amount_cents)
