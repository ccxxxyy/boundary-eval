from typing import Callable
from faultline.api import DurableStore, PaymentGateway, GatewayTimeout

def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    charge_key = f"order:{order_id}:charge_id"
    
    # 1. Check if we already completed the charge and saved the result.
    # If so, we can just return it immediately.
    charge_id = store.get(charge_key)
    if charge_id is not None:
        return charge_id

    # 2. Get or create an idempotency key for this order.
    idem_key_store = f"order:{order_id}:idem_key"
    idem_key = store.get(idem_key_store)
    
    if idem_key is None:
        idem_key = new_id()
        # Persist the idempotency key before making any external calls.
        # If the process crashes after this write, the exact same key will 
        # be read and reused on redelivery, preventing double charges.
        store.put(idem_key_store, idem_key)

    # 3. Interact with the payment gateway safely.
    while True:
        # Always check if the charge was already created. This handles cases where
        # a previous attempt timed out but actually succeeded on the gateway, or 
        # where we crashed after charging but before saving the charge_id locally.
        charge_id = gateway.lookup(idem_key)
        if charge_id is not None:
            break
        
        try:
            # Attempt to create the charge.
            charge_id = gateway.charge(idem_key, amount_cents)
            break
        except GatewayTimeout:
            # The charge might or might not have been created.
            # We loop back around and use lookup() to safely find out.
            continue

    # 4. Persist the result so we don't have to hit the gateway on redelivery.
    store.put(charge_key, charge_id)
    
    return charge_id
