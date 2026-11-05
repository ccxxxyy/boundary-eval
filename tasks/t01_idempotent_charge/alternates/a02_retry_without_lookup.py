"""Known-correct. Never calls `lookup`: relies purely on the gateway
deduplicating repeated calls that share an idempotency key, which the contract
guarantees. Included so the grader cannot get away with requiring a
reconciliation call."""

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

    last: Exception | None = None
    for _ in range(8):
        try:
            return gateway.charge(idempotency_key=key, amount_cents=amount_cents)
        except GatewayTimeout as exc:
            last = exc
    raise RuntimeError(f"gateway unreachable: {last}")
