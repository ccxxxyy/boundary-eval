"""BROKEN. Expected violation: "still holds".

The compensation is there, and it runs after the outcome has been written down.
If the process dies in that window, the redelivery sees a terminal `declined`
and returns immediately - with the seat still held. Nobody is charged, nobody
is notified, and that seat is gone from inventory for good.
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

    for _ in range(6):
        try:
            gateway.charge(idempotency_key=charge_key, amount_cents=amount_cents)
            break
        except ChargeDeclined:
            store.put(state_key, "declined")
            _retry(lambda: inventory.release(booking_id=booking_id))
            return "declined"
        except GatewayTimeout:
            if gateway.lookup(charge_key) is not None:
                break
    else:
        raise RuntimeError("gateway unreachable")

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
