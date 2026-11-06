from typing import Callable

class DurableStore:
    """A durable key-value store."""
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...
    def delete(self, key: str) -> None: ...

class SeatInventory:
    def hold(self, booking_id: str, seat: str) -> None: ...
    def release(self, booking_id: str) -> None: ...
    def held_seat(self, booking_id: str) -> str | None: ...

class PaymentGateway:
    def charge(self, idempotency_key: str, amount_cents: int) -> str: ...
    def lookup(self, idempotency_key: str) -> str | None: ...

class GatewayTimeout(Exception):
    """The gateway did not answer."""

class InventoryTimeout(Exception):
    """The inventory service did not answer."""

class ChargeDeclined(Exception):
    """The gateway refused the charge."""

def book_seat(
    booking_id: str,
    seat: str,
    amount_cents: int,
    store: DurableStore,
    inventory: SeatInventory,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Book `seat` for `booking_id`. Return "confirmed" or "declined"."""
    
    # Retrieve the current state of the booking process.
    state = store.get(booking_id)
    
    # 1. Initial State -> Holding
    if state is None:
        store.put(booking_id, "holding")
        state = "holding"
        
    # 2. Holding -> Charging
    if state == "holding":
        # Hold the seat. Retry on timeout since the operation is idempotent.
        while True:
            try:
                inventory.hold(booking_id, seat)
                break
            except InventoryTimeout:
                continue
                
        # Generate a fresh idempotency key and persist it before charging.
        idem_key = new_id()
        state = f"charging:{idem_key}"
        store.put(booking_id, state)
        
    # 3. Charging -> Confirmed OR Releasing
    if state is not None and state.startswith("charging:"):
        idem_key = state.split(":", 1)[1]
        
        charge_successful = False
        charge_declined = False
        
        while True:
            # Always check if the charge already succeeded to handle ambiguous GatewayTimeouts
            # from previous attempts (or previous process crashes).
            if gateway.lookup(idem_key) is not None:
                charge_successful = True
                break
                
            try:
                gateway.charge(idem_key, amount_cents)
                charge_successful = True
                break
            except GatewayTimeout:
                # The charge might or might not have been applied. 
                # The next loop iteration will verify via gateway.lookup().
                continue
            except ChargeDeclined:
                # The charge was definitively refused. No money moved.
                charge_declined = True
                break
                
        if charge_successful:
            store.put(booking_id, "confirmed")
            state = "confirmed"
        elif charge_declined:
            store.put(booking_id, "releasing")
            state = "releasing"
            
    # 4. Releasing -> Declined
    if state == "releasing":
        # Release the seat. Retry on timeout since the operation is idempotent.
        while True:
            try:
                inventory.release(booking_id)
                break
            except InventoryTimeout:
                continue
                
        store.put(booking_id, "declined")
        state = "declined"
        
    # 5. Terminal States
    if state == "confirmed":
        return "confirmed"
        
    if state == "declined":
        return "declined"
        
    raise RuntimeError(f"Unexpected state: {state}")
