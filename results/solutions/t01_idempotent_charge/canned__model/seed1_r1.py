"""Reference solution.

The idempotency key is durably recorded *before* the first charge attempt, so
every redelivery reuses the same key and the gateway's deduplication can do its
job. An ambiguous timeout is resolved by asking the gateway what happened under
that key rather than by guessing.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, GatewayTimeout, PaymentGateway

MAX_GATEWAY_ATTEMPTS = 8


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    key_slot = f"order:{order_id}:idempotency-key"

    key = store.get(key_slot)
    if key is None:
        candidate = new_id()
        if store.compare_and_set(key_slot, None, candidate):
            key = candidate
        else:
            key = store.get(key_slot)
    assert key is not None

    for _ in range(MAX_GATEWAY_ATTEMPTS):
        try:
            return gateway.charge(idempotency_key=key, amount_cents=amount_cents)
        except GatewayTimeout:
            settled = gateway.lookup(key)
            if settled is not None:
                return settled

    raise RuntimeError(f"gateway unreachable for order {order_id}")
