from __future__ import annotations
from typing import Callable

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
    
    # Recover previous state or initialize a new one
    state_str = store.get(booking_id)
    if state_str is None:
        idemp_key = new_id()
        state_str = f"INIT:{idemp_key}"
        store.put(booking_id, state_str)
        
    # State machine loop
    while True:
        status, idemp_key = state_str.split(":", 1)
        
        if status == "INIT":
            # Check if the hold already succeeded (e.g., if we crashed before saving state, 
            # or if a previous attempt timed out but was actually applied).
            if inventory.held_seat(booking_id) == seat:
                state_str = f"SEAT_HELD:{idemp_key}"
                store.put(booking_id, state_str)
                continue
                
            try:
                inventory.hold(booking_id, seat)
                state_str = f"SEAT_HELD:{idemp_key}"
                store.put(booking_id, state_str)
            except InventoryTimeout:
                continue
                
        elif status == "SEAT_HELD":
            # Check if the charge already succeeded (e.g., if we crashed before saving state,
            # or if a previous attempt timed out but was actually applied).
            if gateway.lookup(idemp_key) is not None:
                state_str = f"CHARGED:{idemp_key}"
                store.put(booking_id, state_str)
                continue
                
            try:
                gateway.charge(idemp_key, amount_cents)
                state_str = f"CHARGED:{idemp_key}"
                store.put(booking_id, state_str)
            except GatewayTimeout:
                continue
            except ChargeDeclined:
                state_str = f"DECLINED:{idemp_key}"
                store.put(booking_id, state_str)
                
        elif status == "CHARGED":
            return "confirmed"
            
        elif status == "DECLINED":
            # Check if the release already succeeded (e.g., if we crashed before saving state,
            # or if a previous attempt timed out but was actually applied).
            if inventory.held_seat(booking_id) is None:
                state_str = f"RELEASED:{idemp_key}"
                store.put(booking_id, state_str)
                continue
                
            try:
                inventory.release(booking_id)
                state_str = f"RELEASED:{idemp_key}"
                store.put(booking_id, state_str)
            except InventoryTimeout:
                continue
                
        elif status == "RELEASED":
            return "declined"
