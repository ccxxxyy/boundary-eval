"""BROKEN. Expected violation: "charged 2 times".

The shape almost every payment-integration guide suggests - "generate a unique
idempotency key for each request" - read as "each call of this function". The
key lives only in memory, so a redelivery after a crash mints a new one and the
gateway has no way to connect the two attempts.
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
    if store.get(f"order:{order_id}:charge") is not None:
        return store.get(f"order:{order_id}:charge")

    key = new_id()
    for _ in range(8):
        try:
            charge_id = gateway.charge(idempotency_key=key, amount_cents=amount_cents)
            break
        except GatewayTimeout:
            settled = gateway.lookup(key)
            if settled is not None:
                charge_id = settled
                break
    else:
        raise RuntimeError("gateway unreachable")

    store.put(f"order:{order_id}:charge", charge_id)
    return charge_id
