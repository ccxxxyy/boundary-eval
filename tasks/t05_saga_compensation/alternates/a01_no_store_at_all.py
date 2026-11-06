"""Known-correct, and it never touches the store.

Both external systems can already answer the questions that matter - "has this
booking been charged?" and "does it hold a seat?" - so there is no local state
worth keeping. Reconciling against the gateway on entry replaces the state
machine entirely.

Included because a grader that expected a durable state machine would call
this unsafe, and it is not.
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
    charge_key = f"charge:{booking_id}"

    if gateway.lookup(charge_key) is not None:
        # Already paid on some earlier attempt. Make sure the seat is there.
        _retry(lambda: inventory.hold(booking_id=booking_id, seat=seat))
        return "confirmed"

    _retry(lambda: inventory.hold(booking_id=booking_id, seat=seat))

    for _ in range(6):
        try:
            gateway.charge(idempotency_key=charge_key, amount_cents=amount_cents)
            return "confirmed"
        except ChargeDeclined:
            _retry(lambda: inventory.release(booking_id=booking_id))
            return "declined"
        except GatewayTimeout:
            if gateway.lookup(charge_key) is not None:
                return "confirmed"
    raise RuntimeError("gateway unreachable")


def _retry(operation) -> None:
    for _ in range(6):
        try:
            operation()
            return
        except InventoryTimeout:
            continue
    raise RuntimeError("inventory unreachable")
