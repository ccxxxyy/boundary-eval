from typing import Callable

def handle_order(
    order_id: str,
    amount_cents: int,
    store: 'DurableStore',
    gateway: 'PaymentGateway',
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
    
    # 1. Durably associate an idempotency key with this order.
    # If we crash before the put() returns, the next run will generate a new key,
    # which is safe because no charge attempt has been made yet.
    # If we crash after put() returns, the next run will reuse the stored key.
    idem_key_store_key = f"order:{order_id}:idem_key"
    idem_key = store.get(idem_key_store_key)
    
    if idem_key is None:
        idem_key = new_id()
        store.put(idem_key_store_key, idem_key)
        
    # 2. Attempt to charge or recover the existing charge.
    # We loop to handle GatewayTimeout internally without letting it escape,
    # ensuring the function runs to completion on transient network errors.
    while True:
        # Always check if the charge was already created. This handles cases where:
        # - A previous attempt timed out but the charge was actually applied.
        # - We crashed after the charge was applied but before we could return.
        # - The queue redelivered the message after a successful charge (e.g., lost ack).
        charge_id = gateway.lookup(idem_key)
        if charge_id is not None:
            return charge_id
            
        try:
            return gateway.charge(idem_key, amount_cents)
        except Exception as e:
            # Catch GatewayTimeout by name so we don't need to import it,
            # strictly following the instruction that the module doesn't need it to run.
            if type(e).__name__ == 'GatewayTimeout':
                continue
            raise
