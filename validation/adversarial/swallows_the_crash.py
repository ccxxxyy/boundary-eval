"""Adversarial input: catches everything, including the simulated crash.

A real killed process cannot keep running, so the harness must refuse to count
this as a pass rather than let it loop until the fault schedule runs out.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, PaymentGateway


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    key = f"charge:{order_id}"
    while True:
        try:
            return gateway.charge(idempotency_key=key, amount_cents=amount_cents)
        except BaseException:  # noqa: BLE001 - the point of this file
            continue
