from __future__ import annotations
from typing import Callable


def _is_exception_type(e: Exception, type_name: str) -> bool:
    return any(cls.__name__ == type_name for cls in type(e).__mro__)


def _ensure_seat_held(inventory: SeatInventory, booking_id: str, seat: str) -> None:
    while inventory.held_seat(booking_id) != seat:
        try:
            inventory.hold(booking_id, seat)
        except Exception as e:
            if _is_exception_type(e, "InventoryTimeout"):
                continue
            raise


def _ensure_seat_released(inventory: SeatInventory, booking_id: str) -> None:
    while inventory.held_seat(booking_id) is not None:
        try:
            inventory.release(booking_id)
        except Exception as e:
            if _is_exception_type(e, "InventoryTimeout"):
                continue
            raise


def _get_or_create_idem_key(
    store: DurableStore, booking_id: str, new_id: Callable[[], str]
) -> str:
    key = f"booking:{booking_id}:idem"
    idem_key = store.get(key)
    if idem_key is not None:
        return idem_key

    fresh_id = new_id()
    if store.compare_and_set(key, None, fresh_id):
        return fresh_id

    idem_key = store.get(key)
    if idem_key is not None:
        return idem_key
    return fresh_id


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
    state_key = f"booking:{booking_id}:state"

    # 1. Check if terminal state is already recorded in durable store
    state = store.get(state_key)
    if state == "CONFIRMED":
        _ensure_seat_held(inventory, booking_id, seat)
        return "confirmed"
    elif state == "DECLINED":
        _ensure_seat_released(inventory, booking_id)
        return "declined"

    # 2. Retrieve or generate a durable idempotency key for payment gateway
    idem_key = _get_or_create_idem_key(store, booking_id, new_id)

    # 3. Check if charge already exists on gateway (e.g. from prior attempt)
    charge_id = gateway.lookup(idem_key)
    if charge_id is not None:
        _ensure_seat_held(inventory, booking_id, seat)
        store.put(state_key, "CONFIRMED")
        return "confirmed"

    # 4. Hold seat in inventory before attempting payment
    _ensure_seat_held(inventory, booking_id, seat)

    # 5. Charge loop handling timeouts and declines
    while True:
        charge_id = gateway.lookup(idem_key)
        if charge_id is not None:
            store.put(state_key, "CONFIRMED")
            _ensure_seat_held(inventory, booking_id, seat)
            return "confirmed"

        state = store.get(state_key)
        if state == "CONFIRMED":
            _ensure_seat_held(inventory, booking_id, seat)
            return "confirmed"
        elif state == "DECLINED":
            _ensure_seat_released(inventory, booking_id)
            return "declined"

        try:
            gateway.charge(idem_key, amount_cents)
            store.put(state_key, "CONFIRMED")
            _ensure_seat_held(inventory, booking_id, seat)
            return "confirmed"
        except Exception as e:
            if _is_exception_type(e, "ChargeDeclined"):
                store.put(state_key, "DECLINED")
                _ensure_seat_released(inventory, booking_id)
                return "declined"
            elif _is_exception_type(e, "GatewayTimeout"):
                continue
            else:
                raise
