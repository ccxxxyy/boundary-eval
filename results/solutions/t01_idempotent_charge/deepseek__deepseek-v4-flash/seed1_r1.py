from __future__ import annotations
from typing import Callable


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` exactly once and return the charge id.

    Uses a durable key‑value store to record an idempotency key and the
    resulting charge id.  The gateway deduplicates on the idempotency key,
    so repeated calls with the same key are safe.  After a timeout we look
    up the charge on the gateway to learn whether it was actually created.
    """
    # Key prefixes for the durable store
    IDEM_KEY_PREFIX = "order_idem_key:"
    CHARGE_ID_PREFIX = "order_charge_id:"

    idem_key_store_key = IDEM_KEY_PREFIX + order_id
    charge_id_store_key = CHARGE_ID_PREFIX + order_id

    # ------------------------------------------------------------------
    # 1. Obtain or create the idempotency key for this order.
    #    The key is stored atomically so that a crash after generation
    #    does not lead to two different keys being used.
    # ------------------------------------------------------------------
    idem_key = store.get(idem_key_store_key)
    if idem_key is None:
        candidate = new_id()
        if store.compare_and_set(idem_key_store_key, None, candidate):
            idem_key = candidate
        else:
            # Another invocation (e.g. after a crash) already set the key.
            idem_key = store.get(idem_key_store_key)
            # It must exist now.
            assert idem_key is not None

    # ------------------------------------------------------------------
    # 2. If we already know the charge id, return it immediately.
    #    This handles redelivery after a crash that occurred after the
    #    charge id was persisted but before the function returned.
    # ------------------------------------------------------------------
    charge_id = store.get(charge_id_store_key)
    if charge_id is not None:
        return charge_id

    # ------------------------------------------------------------------
    # 3. Charge loop.
    #    We call gateway.charge with the idempotency key.  If it times
    #    out we use gateway.lookup to determine whether the charge was
    #    actually created.  If it was not, we retry (the gateway will
    #    deduplicate on the same key).  If it was, we persist the
    #    charge id and return.
    # ------------------------------------------------------------------
    while True:
        try:
            charge_id = gateway.charge(idem_key, amount_cents)
            # Success – persist and return.
            store.put(charge_id_store_key, charge_id)
            return charge_id
        except Exception as exc:
            # The only exception we expect is GatewayTimeout, but we cannot
            # import it directly.  Check by class name.
            if type(exc).__name__ != "GatewayTimeout":
                raise
            # The gateway did not respond; the charge may or may not exist.
            looked_up = gateway.lookup(idem_key)
            if looked_up is not None:
                # The charge was created despite the timeout.
                store.put(charge_id_store_key, looked_up)
                return looked_up
            # The charge was not created – retry the charge call.
            # The loop continues with the same idempotency key.
