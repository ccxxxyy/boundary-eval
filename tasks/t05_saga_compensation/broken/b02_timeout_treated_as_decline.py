"""BROKEN. Expected violation: "paid for nothing".

Collapses two different answers into one. A decline means no money moved; a
timeout means nobody knows. Compensating on both releases a seat the customer
has already been charged for, and `gateway.lookup` - which would have said so -
is never called.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import (
    ChargeDeclined,
    DurableStore,
    GatewayTimeout,
    InventoryTimeout,
    PaymentGateway,
    SeatInventory,
)


def book_seat(
    booking_id: str,
    seat: str,
    amount_cents: int,
    store: DurableStore,
    inventory: SeatInventory,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    state_key = f"booking:{booking_id}:state"
    charge_key = f"charge:{booking_id}"

    settled = store.get(state_key)
    if settled in ("confirmed", "declined"):
        return settled

    _retry(lambda: inventory.hold(booking_id=booking_id, seat=seat))

    try:
        gateway.charge(idempotency_key=charge_key, amount_cents=amount_cents)
    except (ChargeDeclined, GatewayTimeout):
        _retry(lambda: inventory.release(booking_id=booking_id))
        store.put(state_key, "declined")
        return "declined"

    store.put(state_key, "confirmed")
    return "confirmed"


def _retry(operation) -> None:
    for _ in range(6):
        try:
            operation()
            return
        except InventoryTimeout:
            continue
    raise RuntimeError("inventory unreachable")
