from __future__ import annotations

from typing import Callable

try:
    from faultline.api import DurableStore, GatewayTimeout, PaymentGateway
except ImportError:
    class GatewayTimeout(Exception):
        pass


def _is_timeout(exc: Exception) -> bool:
    if GatewayTimeout is not None and isinstance(exc, GatewayTimeout):
        return True
    return type(exc).__name__ == "GatewayTimeout"


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    charge_key = f"order:{order_id}:charge_id"
    existing_charge_id = store.get(charge_key)
    if existing_charge_id is not None:
        return existing_charge_id

    idem_key = f"order:{order_id}:idem_key"
    ik = store.get(idem_key)
    while ik is None:
        candidate = new_id()
        if store.compare_and_set(idem_key, None, candidate):
            ik = candidate
        else:
            ik = store.get(idem_key)

    while True:
        charge_id = gateway.lookup(ik)
        if charge_id is not None:
            break
        try:
            charge_id = gateway.charge(ik, amount_cents)
            break
        except Exception as exc:
            if _is_timeout(exc):
                continue
            raise

    store.put(charge_key, charge_id)
    return charge_id
