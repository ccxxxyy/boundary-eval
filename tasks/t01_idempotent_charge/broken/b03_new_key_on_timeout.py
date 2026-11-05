"""BROKEN. Expected violation: "charged 2 times".

Persists the key correctly, but treats a timeout as "the request did not land"
and retries under a brand new key. That throws away the one mechanism that
would have deduplicated the retry.
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

    for _ in range(8):
        try:
            return gateway.charge(idempotency_key=key, amount_cents=amount_cents)
        except GatewayTimeout:
            key = new_id()
            store.put(slot, key)
    raise RuntimeError("gateway unreachable")
