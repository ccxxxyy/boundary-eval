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
    # 1. Retrieve or generate a durable idempotency key for this order.
    # Because the process can crash at any time, we must persist the key 
    # before making any external calls to the payment gateway.
    idem_key_name = f"idem:{order_id}"
    idem_key = store.get(idem_key_name)
    
    if idem_key is None:
        idem_key = new_id()
        store.put(idem_key_name, idem_key)
        
    # 2. Attempt to charge the customer using the idempotency key.
    # If the process crashes during or after the charge, the queue will redeliver,
    # we will read the same idempotency key from the store, and the gateway will 
    # safely deduplicate the charge.
    while True:
        try:
            return gateway.charge(idem_key, amount_cents)
        except GatewayTimeout:
            # If the gateway times out, the charge may or may not have been created.
            # We use lookup() to check the definitive state.
            charge_id = gateway.lookup(idem_key)
            if charge_id is not None:
                # The charge was successfully created despite the timeout.
                return charge_id
            
            # If lookup() returns None, the charge was not created. 
            # The loop will restart and we will safely retry the charge.
