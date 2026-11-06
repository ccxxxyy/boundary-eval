from __future__ import annotations
from typing import Callable


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id.

    This implementation ensures the customer is charged exactly once by:
    1. Persisting a stable idempotency key for the order_id in the DurableStore.
    2. Using that key for all gateway.charge calls to ensure deduplication.
    3. Handling GatewayTimeout by checking gateway.lookup to verify the state.
    4. Retrying until a definitive charge_id is obtained.
    """

    # 1. Retrieve or establish a stable idempotency key for this order.
    # We must persist the key before the first charge attempt to ensure that
    # even if the process crashes, subsequent retries use the same key.
    store_key = f"payment_idempotency_key:{order_id}"

    idempotency_key = store.get(store_key)
    while idempotency_key is None:
        candidate_key = new_id()
        # Atomic compare_and_set ensures we don't overwrite a key set by a
        # previous run that crashed between store.put and the next step.
        if store.compare_and_set(store_key, None, candidate_key):
            idempotency_key = candidate_key
        else:
            # If CAS failed, someone else (a previous run) set the key.
            idempotency_key = store.get(store_key)

    # 2. Attempt to charge the gateway until we have a definitive result.
    while True:
        try:
            # The gateway deduplicates based on the idempotency_key.
            return gateway.charge(idempotency_key, amount_cents)
        except Exception as e:
            # We catch Exception and check the name to handle GatewayTimeout
            # without strictly requiring the class to be in the namespace,
            # as per the "your module does not need them to run" hint.
            if e.__class__.__name__ != "GatewayTimeout":
                raise

            # On timeout, the charge may or may not have been created.
            # lookup() is guaranteed not to timeout and returns the charge id
            # if it exists, or None if it doesn't.
            charge_id = gateway.lookup(idempotency_key)
            if charge_id is not None:
                return charge_id

            # If lookup returns None, the charge definitely hasn't happened yet.
            # We loop to retry the charge call.
            continue
