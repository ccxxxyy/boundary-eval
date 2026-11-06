import json
from typing import Callable

class DurableStore:
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...
    def delete(self, key: str) -> None: ...

class SeatInventory:
    def hold(self, booking_id: str, seat: str) -> None: ...
    def release(self, booking_id: str) -> None: ...
    def held_seat(self, booking_id: str) -> str | None: ...

class PaymentGateway:
    def charge(self, idempotency_key: str, amount_cents: int) -> str: ...
    def lookup(self, idempotency_key: str) -> str | None: ...

class GatewayTimeout(Exception): ...
class InventoryTimeout(Exception): ...
class ChargeDeclined(Exception): ...

def new_id() -> str: ...

def book_seat(
    booking_id: str,
    seat: str,
    amount_cents: int,
    store: DurableStore,
    inventory: SeatInventory,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    # Helper to read the record for this booking
    def read_record():
        raw = store.get(booking_id)
        if raw is None:
            return None
        return json.loads(raw)

    # Helper to atomically update the record (compare-and-set)
    def update_record(expected, new):
        return store.compare_and_set(
            booking_id,
            json.dumps(expected) if expected is not None else None,
            json.dumps(new)
        )

    # Main logic
    record = read_record()
    if record is not None:
        state = record["state"]
        if state == "confirmed":
            return "confirmed"
        if state == "declined":
            return "declined"
    else:
        # No record yet – start fresh
        idempotency_key = new_id()
        new_record = {
            "state": "hold_pending",
            "seat": seat,
            "amount_cents": amount_cents,
            "idempotency_key": idempotency_key,
        }
        if not update_record(None, new_record):
            # Another redelivery already created the record
            record = read_record()
            if record is None:
                # Should not happen, but fallback
                return "declined"
            state = record["state"]
            if state == "confirmed":
                return "confirmed"
            if state == "declined":
                return "declined"
        else:
            record = new_record

    # At this point we have a record with state != confirmed/declined
    state = record["state"]
    idempotency_key = record["idempotency_key"]

    # ---------- HOLD step ----------
    if state == "hold_pending":
        # Attempt to hold the seat
        hold_success = False
        try:
            inventory.hold(booking_id, seat)
            hold_success = True
        except InventoryTimeout:
            # Timeout – check if the hold actually took effect
            held = inventory.held_seat(booking_id)
            if held == seat:
                hold_success = True
            else:
                hold_success = False

        if hold_success:
            # Move to hold_done
            new_record = dict(record)
            new_record["state"] = "hold_done"
            if not update_record(record, new_record):
                # Another redelivery changed state – re-read and continue
                record = read_record()
                if record is None:
                    return "declined"
                state = record["state"]
                if state == "confirmed":
                    return "confirmed"
                if state == "declined":
                    return "declined"
                # Fall through to next state
            else:
                record = new_record
                state = "hold_done"
        else:
            # Hold failed – decline
            new_record = dict(record)
            new_record["state"] = "declined"
            update_record(record, new_record)  # best effort
            return "declined"

    # ---------- CHARGE step ----------
    if state == "hold_done":
        # Move to charge_pending
        new_record = dict(record)
        new_record["state"] = "charge_pending"
        if not update_record(record, new_record):
            record = read_record()
            if record is None:
                return "declined"
            state = record["state"]
            if state == "confirmed":
                return "confirmed"
            if state == "declined":
                return "declined"
        else:
            record = new_record
            state = "charge_pending"

    if state == "charge_pending":
        # Attempt charge
        charge_success = False
        charge_declined = False
        charge_id = None
        try:
            charge_id = gateway.charge(idempotency_key, amount_cents)
            charge_success = True
        except ChargeDeclined:
            charge_declined = True
        except GatewayTimeout:
            # Timeout – check if charge was actually created
            existing = gateway.lookup(idempotency_key)
            if existing is not None:
                charge_id = existing
                charge_success = True
            else:
                charge_success = False

        if charge_success:
            # Charge succeeded – confirm
            new_record = dict(record)
            new_record["state"] = "confirmed"
            new_record["charge_id"] = charge_id
            update_record(record, new_record)
            return "confirmed"
        elif charge_declined:
            # Charge declined – release hold and decline
            try:
                inventory.release(booking_id)
            except InventoryTimeout:
                # Best effort – release is idempotent, will be retried on redelivery
                pass
            new_record = dict(record)
            new_record["state"] = "declined"
            update_record(record, new_record)
            return "declined"
        else:
            # Charge timed out and was not created – release hold and decline
            try:
                inventory.release(booking_id)
            except InventoryTimeout:
                pass
            new_record = dict(record)
            new_record["state"] = "declined"
            update_record(record, new_record)
            return "declined"

    # Should never reach here
    return "declined"
