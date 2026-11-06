from typing import Callable

# Define the exceptions if they are not already provided in the environment.
# This prevents NameError while avoiding shadowing injected classes from the test runner.
try:
    GatewayTimeout  # type: ignore
except NameError:
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
    store: 'DurableStore',
    inventory: 'SeatInventory',
    gateway: 'PaymentGateway',
    new_id: Callable[[], str],
) -> str:
    """Book `seat` for `booking_id`. Return "confirmed" or "declined"."""
    
    # 1. Ensure the seat is held before any payment attempt.
    # This guarantees that if a charge is ever created, the seat is already held,
    # satisfying the invariant: "Under no circumstances does a charge exist while 
    # the booking holds no seat."
    while True:
        try:
            inventory.hold(booking_id, seat)
            break
        except InventoryTimeout:
            continue

    # 2. Get or create a durable idempotency key for the payment gateway.
    # If we crash after generating it but before storing it, the key is lost, 
    # but since it was never sent to the gateway, no charge could exist.
    ik_key = f"ik_{booking_id}"
    ik = store.get(ik_key)
    if not ik:
        ik = new_id()
        store.put(ik_key, ik)

    # 3. Attempt to charge the customer.
    while True:
        try:
            gateway.charge(ik, amount_cents)
            # If the charge succeeds, the seat is already held.
            return "confirmed"
            
        except GatewayTimeout:
            # The charge might have succeeded, failed, or been dropped.
            # We check lookup to see if it succeeded.
            if gateway.lookup(ik) is not None:
                return "confirmed"
            # If it didn't succeed (lookup returned None), we loop and retry the charge.
            # The gateway deduplicates on `ik`, so retrying is perfectly safe.
            continue
            
        except ChargeDeclined:
            # The charge was declined. The API guarantees no money moved.
            # We must release the seat and return "declined".
            while True:
                try:
                    inventory.release(booking_id)
                    break
                except InventoryTimeout:
                    continue
            return "declined"
