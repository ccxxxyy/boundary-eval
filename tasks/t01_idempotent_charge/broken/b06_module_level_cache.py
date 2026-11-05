"""BROKEN. Expected violation: "charged 2 times".

Caches the idempotency key in a module-level dict. This passes any test that
calls the handler twice in one process, including a hand-written "redelivery"
test, and fails the moment the process actually restarts.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, GatewayTimeout, PaymentGateway

_KEYS: dict[str, str] = {}


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    key = _KEYS.get(order_id)
    if key is None:
        key = new_id()
        _KEYS[order_id] = key

    for _ in range(8):
        try:
            return gateway.charge(idempotency_key=key, amount_cents=amount_cents)
        except GatewayTimeout:
            settled = gateway.lookup(key)
            if settled is not None:
                return settled
    raise RuntimeError("gateway unreachable")
