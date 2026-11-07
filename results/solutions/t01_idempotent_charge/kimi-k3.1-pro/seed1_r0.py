"""Crash-safe payment handling using a durable idempotency key."""

from typing import Callable

from faultline.api import DurableStore, GatewayTimeout, PaymentGateway


_IDEMPOTENCY_PREFIX = "handle_order:idempotency:"
_CHARGE_ID_PREFIX = "handle_order:charge_id:"


def _get_or_create_idempotency_key(
    store: DurableStore,
    storage_key: str,
    new_id: Callable[[], str],
) -> str:
    """Return the durable key for this order, creating it if necessary."""
    while True:
        existing = store.get(storage_key)
        if existing is not None:
            return existing

        candidate = new_id()
        if store.compare_and_set(storage_key, None, candidate):
            return candidate
        # If another write won the race, reread rather than replacing its key.


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge ``amount_cents`` for ``order_id`` and return the charge id."""
    charge_storage_key = _CHARGE_ID_PREFIX + order_id

    # This also handles redelivery after a crash or lost acknowledgement.
    saved_charge_id = store.get(charge_storage_key)
    if saved_charge_id is not None:
        return saved_charge_id

    # The key is durable before any charge call. Therefore, even if the
    # process dies after the gateway applies a charge, every retry can reuse
    # the same gateway idempotency key.
    idempotency_key = _get_or_create_idempotency_key(
        store,
        _IDEMPOTENCY_PREFIX + order_id,
        new_id,
    )

    while True:
        try:
            charge_id = gateway.charge(idempotency_key, amount_cents)
        except GatewayTimeout:
            # The request may have been applied. Recover its id if possible;
            # otherwise retry with the same key, which cannot create a second
            # charge even if the timed-out request was in fact applied.
            recovered_charge_id = gateway.lookup(idempotency_key)
            if recovered_charge_id is None:
                continue
            charge_id = recovered_charge_id

        # Persist the result before returning. If the process dies before this
        # write takes effect, a retry repeats the idempotent gateway call.
        store.put(charge_storage_key, charge_id)
        return charge_id
