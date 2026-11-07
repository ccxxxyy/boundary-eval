import json
from typing import Callable

from faultline.api import (
    ChargeDeclined,
    DurableStore,
    GatewayTimeout,
    InventoryTimeout,
    PaymentGateway,
    SeatInventory,
)


def _encode(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def _decode(data: str) -> dict:
    return json.loads(data)


def _load_or_create(
    booking_id: str,
    seat: str,
    amount_cents: int,
    store: DurableStore,
    new_id: Callable[[], str],
) -> dict:
    raw = store.get(booking_id)
    if raw is not None:
        return _decode(raw)

    record = {
        "seat": seat,
        "amount_cents": amount_cents,
        "idem_key": new_id(),
        "phase": "pending",
    }
    store.put(booking_id, _encode(record))
    return record


def _ensure_held(booking_id: str, seat: str, inventory: SeatInventory) -> None:
    while True:
        try:
            inventory.hold(booking_id, seat)
            return
        except InventoryTimeout:
            if inventory.held_seat(booking_id) == seat:
                return


def _ensure_released(booking_id: str, inventory: SeatInventory) -> None:
    while True:
        try:
            inventory.release(booking_id)
            return
        except InventoryTimeout:
            if inventory.held_seat(booking_id) is None:
                return


def _resolve_charge(record: dict, gateway: PaymentGateway) -> str:
    idem_key = record["idem_key"]
    amount_cents = record["amount_cents"]

    if gateway.lookup(idem_key) is not None:
        return "confirmed"

    while True:
        try:
            gateway.charge(idem_key, amount_cents)
            return "confirmed"
        except GatewayTimeout:
            if gateway.lookup(idem_key) is not None:
                return "confirmed"
        except ChargeDeclined:
            return "declined"


def book_seat(
    booking_id: str,
    seat: str,
    amount_cents: int,
    store: DurableStore,
    inventory: SeatInventory,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    record = _load_or_create(booking_id, seat, amount_cents, store, new_id)

    if record["phase"] == "declined":
        _ensure_released(booking_id, inventory)
        return "declined"

    _ensure_held(booking_id, seat, inventory)
    outcome = _resolve_charge(record, gateway)

    if outcome == "confirmed":
        return "confirmed"

    record["phase"] = "declined"
    store.put(booking_id, _encode(record))
    _ensure_released(booking_id, inventory)
    return "declined"
