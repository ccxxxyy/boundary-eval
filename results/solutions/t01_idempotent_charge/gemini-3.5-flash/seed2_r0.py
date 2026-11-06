from typing import Callable, Any

try:
    from faultline.api import DurableStore, PaymentGateway, GatewayTimeout
except ImportError:
    class GatewayTimeout(Exception):
        """Fallback definition if faultline.api is not present."""
        pass
    DurableStore = Any  # type: ignore
    PaymentGateway = Any  # type: ignore


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    # 1. Fast path: return immediately if charge ID was already stored
    charge_key = f"charge:{order_id}"
    charge_id = store.get(charge_key)
    if charge_id is not None:
        return charge_id

    # 2. Ensure a durable idempotency key exists for this order before contacting gateway
    ik_key = f"ik:{order_id}"
    ik = store.get(ik_key)
    while ik is None:
        proposed = new_id()
        if store.compare_and_set(ik_key, None, proposed):
            ik = proposed
        else:
            ik = store.get(ik_key)

    # 3. Attempt to charge or locate existing charge on gateway until confirmed
    while True:
        charge_id = gateway.lookup(ik)
        if charge_id is not None:
            store.put(charge_key, charge_id)
            return charge_id

        try:
            charge_id = gateway.charge(ik, amount_cents)
            store.put(charge_key, charge_id)
            return charge_id
        except Exception as e:
            if type(e).__name__ == "GatewayTimeout" or isinstance(e, GatewayTimeout):
                pass
            else:
                raise
