from __future__ import annotations

from collections.abc import Callable


class GatewayTimeout(Exception):
    """The gateway did not answer."""


class InventoryTimeout(Exception):
    """The inventory service did not answer."""


class ChargeDeclined(Exception):
    """The gateway refused the charge. No money moved, and presenting the same
    idempotency key again gets the same refusal."""


class DurableStore:
    """A durable key-value store.

    Each operation is atomic, and once it returns, its effect is durable: it
    survives a process crash. The four methods below are the whole API.
    """

    def get(self, key: str) -> str | None:
        raise NotImplementedError

    def put(self, key: str, value: str) -> None:
        raise NotImplementedError

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class SeatInventory:
    def hold(self, booking_id: str, seat: str) -> None:
        raise NotImplementedError

    def release(self, booking_id: str) -> None:
        raise NotImplementedError

    def held_seat(self, booking_id: str) -> str | None:
        raise NotImplementedError


class PaymentGateway:
    def charge(self, idempotency_key: str, amount_cents: int) -> str:
        raise NotImplementedError

    def lookup(self, idempotency_key: str) -> str | None:
        raise NotImplementedError


def _is_inventory_timeout(exc: BaseException) -> bool:
    return isinstance(exc, InventoryTimeout) or type(exc).__name__ == "InventoryTimeout"


def _is_gateway_timeout(exc: BaseException) -> bool:
    return isinstance(exc, GatewayTimeout) or type(exc).__name__ == "GatewayTimeout"


def _is_charge_declined(exc: BaseException) -> bool:
    return isinstance(exc, ChargeDeclined) or type(exc).__name__ == "ChargeDeclined"


def _release_until_free(booking_id: str, inventory: SeatInventory) -> None:
    while inventory.held_seat(booking_id) is not None:
        try:
            inventory.release(booking_id)
        except Exception as exc:
            if not _is_inventory_timeout(exc):
                raise


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
    key = f"booking:{booking_id}"
    state = store.get(key)

    if state is None:
        idem_key = new_id()
        state = f"PENDING:{idem_key}"
        store.put(key, state)

    if state == "DECLINED":
        _release_until_free(booking_id, inventory)
        return "declined"

    idem_key = state.split(":", 1)[1]

    while inventory.held_seat(booking_id) != seat:
        try:
            inventory.hold(booking_id, seat)
        except Exception as exc:
            if not _is_inventory_timeout(exc):
                raise

    while gateway.lookup(idem_key) is None:
        try:
            gateway.charge(idem_key, amount_cents)
            return "confirmed"
        except Exception as exc:
            if _is_charge_declined(exc):
                store.put(key, "DECLINED")
                _release_until_free(booking_id, inventory)
                return "declined"
            if not _is_gateway_timeout(exc):
                raise

    return "confirmed"
