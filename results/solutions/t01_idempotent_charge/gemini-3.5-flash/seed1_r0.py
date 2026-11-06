from __future__ import annotations

from typing import Callable

try:
    from faultline.api import DurableStore, GatewayTimeout, PaymentGateway
except ImportError:
    class GatewayTimeout(Exception):
        pass

    DurableStore = object  # type: ignore
    PaymentGateway = object  # type: ignore


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    charge_key = f"order:{order_id}:charge_id"
    ik_key = f"order:{order_id}:idempotency_key"

    # 1. Fast path: check if charge_id was already persisted from a prior run.
    existing_charge_id = store.get(charge_key)
    if existing_charge_id is not None:
        return existing_charge_id

    # 2. Retrieve or atomically generate a durable idempotency key for this order.
    ik = store.get(ik_key)
    while ik is None:
        candidate = new_id()
        if store.compare_and_set(ik_key, None, candidate):
            ik = candidate
        else:
            ik = store.get(ik_key)

    # 3. Ensure the charge is created on the gateway using the fixed idempotency key.
    while True:
        charge_id = gateway.lookup(ik)
        if charge_id is not None:
            break
        try:
            charge_id = gateway.charge(ik, amount_cents)
            break
        except Exception as exc:
            if type(exc).__name__ == "GatewayTimeout" or isinstance(exc, GatewayTimeout):
                pass
            else:
                raise

    # 4. Save the charge_id to store for fast-path retrieval on future redeliveries.
    store.put(charge_key, charge_id)
    return charge_id
