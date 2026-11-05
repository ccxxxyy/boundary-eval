"""Known-correct, deliberately different in shape from reference.py.

Derives the idempotency key from the order id instead of storing a generated
one, so it never touches the store at all. The grader must accept this: it is
correct, and a grader that only recognises the reference's shape would be
producing false failures.
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
    key = f"charge:{order_id}"
    for _ in range(8):
        try:
            return gateway.charge(idempotency_key=key, amount_cents=amount_cents)
        except GatewayTimeout:
            settled = gateway.lookup(key)
            if settled is not None:
                return settled
    raise RuntimeError("gateway unreachable")
