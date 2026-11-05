"""BROKEN. Expected violation: "charged 2 times".

Does store the idempotency key, but writes it after the charge has been
attempted. The window between the charge taking effect and the key becoming
durable is exactly where the second charge comes from.
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

    store.put(slot, key)
    return charge_id
