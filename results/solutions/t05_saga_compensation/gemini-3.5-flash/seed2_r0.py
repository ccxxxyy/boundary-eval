from typing import Any, Callable


class GatewayTimeout(Exception):
    """The gateway did not answer."""


class InventoryTimeout(Exception):
    """The inventory service did not answer."""


class ChargeDeclined(Exception):
    """The gateway refused the charge."""


class DurableStore:
    pass


class SeatInventory:
    pass


class PaymentGateway:
    pass


def _is_inventory_timeout(e: Exception) -> bool:
    return any(cls.__name__ == "InventoryTimeout" for cls in type(e).__mro__)


def _is_gateway_timeout(e: Exception) -> bool:
    return any(cls.__name__ == "GatewayTimeout" for cls in type(e).__mro__)


def _is_charge_declined(e: Exception) -> bool:
    return any(cls.__name__ == "ChargeDeclined" for cls in type(e).__mro__)


def _ensure_seat_held(inventory: Any, booking_id: str, seat: str) -> None:
    while True:
        try:
            if inventory.held_seat(booking_id) == seat:
                return
        except Exception:
            pass

        try:
            inventory.hold(booking_id, seat)
        except Exception as e:
            if _is_inventory_timeout(e):
                pass
            else:
                raise

        try:
            if inventory.held_seat(booking_id) == seat:
                return
        except Exception:
            pass


def _ensure_seat_released(inventory: Any, booking_id: str) -> None:
    while True:
        try:
            if inventory.held_seat(booking_id) is None:
                return
        except Exception:
            pass

        try:
            inventory.release(booking_id)
        except Exception as e:
            if _is_inventory_timeout(e):
                pass
            else:
                raise

        try:
            if inventory.held_seat(booking_id) is None:
                return
        except Exception:
            pass


def _resolve_payment(gateway: Any, idem_key: str, amount_cents: int) -> bool:
    while True:
        try:
            charge_id = gateway.lookup(idem_key)
            if charge_id is not None:
                return True
        except Exception:
            pass

        try:
            gateway.charge(idem_key, amount_cents)
            return True
        except Exception as e:
            if _is_gateway_timeout(e):
                try:
                    charge_id = gateway.lookup(idem_key)
                    if charge_id is not None:
                        return True
                except Exception:
                    pass
                continue
            elif _is_charge_declined(e):
                return False
            else:
                raise


def book_seat(
    booking_id: str,
    seat: str,
    amount_cents: int,
    store: Any,
    inventory: Any,
    gateway: Any,
    new_id: Callable[[], str],
) -> str:
    """Book `seat` for `booking_id`. Return "confirmed" or "declined"."""
    status_key = f"status:{booking_id}"
    idem_store_key = f"idem:{booking_id}"

    # Step 0: Check if final status is already stored
    status = store.get(status_key)
    if status == "confirmed":
        _ensure_seat_held(inventory, booking_id, seat)
        return "confirmed"
    elif status == "declined":
        _ensure_seat_released(inventory, booking_id)
        return "declined"

    # Step 1: Guarantee seat is held before payment attempt
    _ensure_seat_held(inventory, booking_id, seat)

    # Step 2: Retrieve or generate durable idempotency key
    idem_key = store.get(idem_store_key)
    if idem_key is None:
        idem_key = new_id()
        store.put(idem_store_key, idem_key)

    # Step 3: Attempt payment resolution
    is_confirmed = _resolve_payment(gateway, idem_key, amount_cents)

    # Step 4: Record terminal state and align seat reservation accordingly
    if is_confirmed:
        store.put(status_key, "confirmed")
        _ensure_seat_held(inventory, booking_id, seat)
        return "confirmed"
    else:
        _ensure_seat_released(inventory, booking_id)
        store.put(status_key, "declined")
        return "declined"
