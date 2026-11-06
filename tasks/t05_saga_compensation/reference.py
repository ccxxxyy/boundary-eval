"""Reference solution.

Two orderings carry it:

  * the seat is held before the charge, so a confirmed booking always has a
    seat behind it;
  * the release happens before `declined` is written down, so a redelivery can
    never find a terminal state with the compensation only half done.

And one distinction: a decline is final, a timeout is not. The declined branch
compensates immediately; the timeout branch asks the gateway what actually
happened rather than guessing, because guessing "it failed" would release a
seat the customer has paid for.
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

CONFIRMED = "confirmed"
DECLINED = "declined"
MAX_RETRIES = 6


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
    if settled in (CONFIRMED, DECLINED):
        return settled

    _hold(inventory, booking_id, seat)

    for _ in range(MAX_RETRIES):
        try:
            gateway.charge(idempotency_key=charge_key, amount_cents=amount_cents)
            break
        except ChargeDeclined:
            # Final answer: no money moved and it never will under this key.
            # Give the seat back before recording the outcome, so a redelivery
            # cannot find a terminal state with the seat still held.
            _release(inventory, booking_id)
            store.put(state_key, DECLINED)
            return DECLINED
        except GatewayTimeout:
            # Not a final answer. Ask rather than assume: treating this as a
            # failure would release a seat that may already be paid for.
            if gateway.lookup(charge_key) is not None:
                break
    else:
        raise RuntimeError(f"gateway unreachable for booking {booking_id}")

    store.put(state_key, CONFIRMED)
    return CONFIRMED


def _hold(inventory: SeatInventory, booking_id: str, seat: str) -> None:
    for _ in range(MAX_RETRIES):
        try:
            inventory.hold(booking_id=booking_id, seat=seat)
            return
        except InventoryTimeout:
            continue  # idempotent, so retrying is always safe
    raise RuntimeError("inventory unreachable")


def _release(inventory: SeatInventory, booking_id: str) -> None:
    for _ in range(MAX_RETRIES):
        try:
            inventory.release(booking_id=booking_id)
            return
        except InventoryTimeout:
            continue  # idempotent, so retrying is always safe
    raise RuntimeError("inventory unreachable")
