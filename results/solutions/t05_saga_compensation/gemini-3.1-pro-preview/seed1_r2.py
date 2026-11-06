from typing import Callable

def book_seat(
    booking_id: str,
    seat: str,
    amount_cents: int,
    store: 'DurableStore',
    inventory: 'SeatInventory',
    gateway: 'PaymentGateway',
    new_id: Callable[[], str],
) -> str:
    """Book `seat` for `booking_id`. Return "confirmed" or "declined"."""
    status_key = f"status:{booking_id}"
    ik_key = f"ik:{booking_id}"
    
    # 1. Check if we already have a final status from a previous attempt
    status = store.get(status_key)
    if status == "confirmed":
        return "confirmed"
    if status == "declined":
        # Ensure the seat is released before returning
        while inventory.held_seat(booking_id) is not None:
            try:
                inventory.release(booking_id)
            except Exception as e:
                if type(e).__name__ == 'InventoryTimeout':
                    pass
                else:
                    raise
        return "declined"
        
    # 2. Get or create a durable idempotency key for the payment gateway
    ik = store.get(ik_key)
    if not ik:
        ik = new_id()
        store.put(ik_key, ik)
        
    # 3. Hold the seat (must be done before charging to guarantee we have it)
    while inventory.held_seat(booking_id) != seat:
        try:
            inventory.hold(booking_id, seat)
        except Exception as e:
            if type(e).__name__ == 'InventoryTimeout':
                pass
            else:
                raise
            
    # 4. Charge the customer or verify an existing charge
    while True:
        # Always check if the charge already exists (e.g., from a previous timeout)
        charge_id = gateway.lookup(ik)
        if charge_id:
            store.put(status_key, "confirmed")
            return "confirmed"
            
        try:
            gateway.charge(ik, amount_cents)
            store.put(status_key, "confirmed")
            return "confirmed"
        except Exception as e:
            if type(e).__name__ == 'GatewayTimeout':
                # The outcome is unknown. Loop around and use lookup() to check.
                pass
            elif type(e).__name__ == 'ChargeDeclined':
                # The charge was definitively refused.
                store.put(status_key, "declined")
                
                # We must release the seat since the customer didn't pay
                while inventory.held_seat(booking_id) is not None:
                    try:
                        inventory.release(booking_id)
                    except Exception as e2:
                        if type(e2).__name__ == 'InventoryTimeout':
                            pass
                        else:
                            raise
                return "declined"
            else:
                raise
