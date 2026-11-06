from typing import Any, Callable


class DurableStore:
    pass


class SeatInventory:
    pass


class PaymentGateway:
    pass


class GatewayTimeout(Exception):
    pass


class InventoryTimeout(Exception):
    pass


class ChargeDeclined(Exception):
    pass


def _is_exc(e: Exception, name: str) -> bool:
    return any(base.__name__ == name for base in type(e).__mro__)


def _hold_seat(inventory: Any, booking_id: str, seat: str) -> None:
    while inventory.held_seat(booking_id) != seat:
        try:
            inventory.hold(booking_id, seat)
        except Exception as e:
            if _is_exc(e, "InventoryTimeout"):
                continue
            raise e


def _release_seat(inventory: Any, booking_id: str) -> None:
    while inventory.held_seat(booking_id) is not None:
        try:
            inventory.release(booking_id)
        except Exception as e:
            if _is_exc(e, "InventoryTimeout"):
                continue
            raise e


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
    status_key = f"booking:{booking_id}:status"
    idem_store_key = f"booking:{booking_id}:idem"

    status = store.get(status_key)
    if status == "confirmed":
        _hold_seat(inventory, booking_id, seat)
        return "confirmed"
    if status == "declined":
        _release_seat(inventory, booking_id)
        return "declined"

    # Hold the seat first to satisfy invariant:
    # Under no circumstances does a charge exist while the booking holds no seat.
    _hold_seat(inventory, booking_id, seat)

    idem_key = store.get(idem_store_key)
    if idem_key is None:
        candidate = new_id()
        if store.compare_and_set(idem_store_key, None, candidate):
            idem_key = candidate
        else:
            idem_key = store.get(idem_store_key)

    while True:
        charge_id = gateway.lookup(idem_key)
        if charge_id is not None:
            store.put(status_key, "confirmed")
            return "confirmed"

        try:
            gateway.charge(idem_key, amount_cents)
            store.put(status_key, "confirmed")
            return "confirmed"
        except Exception as e:
            if _is_exc(e, "ChargeDeclined"):
                _release_seat(inventory, booking_id)
                store.put(status_key, "declined")
                return "declined"
            elif _is_exc(e, "GatewayTimeout"):
                continue
            else:
                raise e
