from collections.abc import Callable
from faultline.api import DurableStore, GatewayTimeout, PaymentGateway

_IDEM_PREFIX = "idem:"
_CHARGE_PREFIX = "charge:"


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    record = store.get(order_id)
    if record is not None and record.startswith(_CHARGE_PREFIX):
        return record[len(_CHARGE_PREFIX) :]

    charge_id: str | None = None
    if record is not None and record.startswith(_IDEM_PREFIX):
        idem_key = record[len(_IDEM_PREFIX) :]
        charge_id = gateway.lookup(idem_key)
    else:
        idem_key = new_id()
        store.put(order_id, f"{_IDEM_PREFIX}{idem_key}")

    while charge_id is None:
        try:
            charge_id = gateway.charge(idem_key, amount_cents)
        except GatewayTimeout:
            charge_id = gateway.lookup(idem_key)

    store.put(order_id, f"{_CHARGE_PREFIX}{charge_id}")
    return charge_id
