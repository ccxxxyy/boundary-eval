from typing import Callable, Any

try:
    from faultline.api import DurableStore, GatewayTimeout, PaymentGateway
except ImportError:
    DurableStore = Any  # type: ignore
    PaymentGateway = Any  # type: ignore

    class GatewayTimeout(Exception):
        pass


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, GatewayTimeout) or type(exc).__name__ == "GatewayTimeout"


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    key_idem = f"order:{order_id}:idem_key"
    key_charge = f"order:{order_id}:charge_id"

    # Fast path: return immediately if charge_id is already stored durably
    charge_id = store.get(key_charge)
    if charge_id is not None:
        return charge_id

    # Ensure a single idempotency key is assigned to this order and persisted
    idem_key = store.get(key_idem)
    if idem_key is None:
        candidate = new_id()
        if store.compare_and_set(key_idem, None, candidate):
            idem_key = candidate
        else:
            idem_key = store.get(key_idem) or candidate

    # Repeatedly attempt gateway operations until confirmed
    while True:
        # Lookup first in case a prior request succeeded before timing out or crashing
        charge_id = gateway.lookup(idem_key)
        if charge_id is not None:
            store.put(key_charge, charge_id)
            return charge_id

        try:
            charge_id = gateway.charge(idem_key, amount_cents)
            store.put(key_charge, charge_id)
            return charge_id
        except Exception as exc:
            if _is_timeout(exc):
                continue
            raise
