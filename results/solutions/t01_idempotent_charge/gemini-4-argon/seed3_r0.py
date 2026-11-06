from collections.abc import Callable
from faultline.api import DurableStore, GatewayTimeout, PaymentGateway


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    state = store.get(order_id)
    if state is not None and state.startswith("done:"):
        return state[5:]

    if state is None:
        idem_key = new_id()
        store.put(order_id, f"idem:{idem_key}")
        charge_id = None
    else:
        idem_key = state[5:]
        charge_id = gateway.lookup(idem_key)

    while charge_id is None:
        try:
            charge_id = gateway.charge(idem_key, amount_cents)
        except GatewayTimeout:
            charge_id = gateway.lookup(idem_key)

    store.put(order_id, f"done:{charge_id}")
    return charge_id
