from collections.abc import Callable

from faultline.api import DurableStore, GatewayTimeout, PaymentGateway

_IDEMPOTENCY_KEY_PREFIX = "payment_pipeline.order.idempotency_key:"


def _ensure_idempotency_key(
    order_id: str,
    store: DurableStore,
    new_id: Callable[[], str],
) -> str:
    """
    Durably associate exactly one gateway idempotency key with this order.

    The key is created before any charge attempt, so every retry after a crash
    or timeout uses the same gateway idempotency key.
    """
    key = _IDEMPOTENCY_KEY_PREFIX + order_id

    while True:
        existing = store.get(key)
        if existing is not None:
            return existing

        candidate = new_id()
        if store.compare_and_set(key, None, candidate):
            return candidate

        # If CAS failed, the key now exists; loop and read it.


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    idempotency_key = _ensure_idempotency_key(order_id, store, new_id)

    while True:
        try:
            return gateway.charge(idempotency_key, amount_cents)
        except GatewayTimeout:
            # The charge may or may not have been created. The gateway's
            # idempotency key makes retrying safe; lookup lets us recover
            # without relying on another successful charge call.
            charge_id = gateway.lookup(idempotency_key)
            if charge_id is not None:
                return charge_id

            # No charge exists yet for this idempotency key; retry.
