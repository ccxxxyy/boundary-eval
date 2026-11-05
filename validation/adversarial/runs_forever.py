"""Adversarial input: never terminates, and keeps hitting the store while it
spins. The operation budget must stop it so one bad solution cannot hang the
whole run."""

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
    counter = 0
    while True:
        store.put(f"spin:{counter}", "x")
        counter += 1
