"""BROKEN. Expected violation: "never charged".

Writes the "already handled" marker before doing the work it guards. A crash in
between leaves an order that everyone believes is paid and that nobody ever
charged. The money is lost in the other direction, which is why checking only
for double charges is not enough.
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
    slot = f"order:{order_id}"
    done = store.get(slot)
    if done is not None:
        return done

    key = f"charge:{order_id}"
    store.put(slot, "pending")

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

    store.put(slot, charge_id)
    return charge_id
