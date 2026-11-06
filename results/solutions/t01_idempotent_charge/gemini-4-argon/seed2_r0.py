from collections.abc import Callable

try:
    from faultline.api import DurableStore, GatewayTimeout, PaymentGateway
except ImportError:  # pragma: no cover
    DurableStore = object  # type: ignore[misc,assignment]
    PaymentGateway = object  # type: ignore[misc,assignment]

    class GatewayTimeout(Exception):  # type: ignore[no-redef]
        pass


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    done_key = f"charge:{order_id}"
    idem_key_name = f"idem:{order_id}"

    charge_id = store.get(done_key)
    if charge_id is not None:
        return charge_id

    idem_key = store.get(idem_key_name)
    if idem_key is None:
        idem_key = new_id()
        store.put(idem_key_name, idem_key)

    while True:
        try:
            charge_id = gateway.charge(idem_key, amount_cents)
            break
        except GatewayTimeout:
            charge_id = gateway.lookup(idem_key)
            if charge_id is not None:
                break

    store.put(done_key, charge_id)
    return charge_id
