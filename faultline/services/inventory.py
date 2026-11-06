"""A seat inventory service.

Holds and releases are both idempotent and both keyed by the booking, so there
is no claim-before-act problem here. That is deliberate: this service exists to
make the *compensation* the interesting part, not the reservation.

A service only honours the fault kinds it understands. The inventory ignores
`"declined"`, which is a payment outcome, so a task can aim a decline at a
call index without having to know which service ends up at that index.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import InventoryTimeout
from ..world import World


@dataclass
class InventoryState:
    holds: dict[str, str] = field(default_factory=dict)  # booking id -> seat
    released: set[str] = field(default_factory=set)

    def describe(self) -> str:
        if not self.holds:
            return "seats held: none"
        rendered = ", ".join(f"{seat} (booking {booking})" for booking, seat in sorted(self.holds.items()))
        return f"seats held: {rendered}"


class SeatInventory:
    def __init__(self, world: World, state: InventoryState) -> None:
        self._world = world
        self._state = state

    def hold(self, booking_id: str, seat: str) -> None:
        """Reserve `seat` for `booking_id`.

        Idempotent: holding the same seat for the same booking twice is one
        hold. May raise `InventoryTimeout`.
        """
        world = self._world
        call_index = world.next_remote_call()
        event = world.begin_op(
            "inventory.hold", f"booking={booking_id!r} seat={seat!r}", mutating=True
        )
        kind = world.fault.timeout_for(call_index)

        if kind == "lost":
            event.outcome = "TIMEOUT (seat not held)"
            raise InventoryTimeout("no response from inventory")

        self._state.holds[booking_id] = seat
        self._state.released.discard(booking_id)

        if kind == "applied":
            event.outcome = "TIMEOUT (but the seat WAS held)"
            raise InventoryTimeout("no response from inventory")

        event.outcome = "ok"

    def release(self, booking_id: str) -> None:
        """Give the seat back.

        Idempotent: releasing an unknown or already-released booking does
        nothing. May raise `InventoryTimeout`.
        """
        world = self._world
        call_index = world.next_remote_call()
        event = world.begin_op("inventory.release", f"booking={booking_id!r}", mutating=True)
        kind = world.fault.timeout_for(call_index)

        if kind == "lost":
            event.outcome = "TIMEOUT (seat not released)"
            raise InventoryTimeout("no response from inventory")

        self._state.holds.pop(booking_id, None)
        self._state.released.add(booking_id)

        if kind == "applied":
            event.outcome = "TIMEOUT (but the seat WAS released)"
            raise InventoryTimeout("no response from inventory")

        event.outcome = "ok"

    def held_seat(self, booking_id: str) -> str | None:
        """Which seat this booking currently holds, if any. Never times out."""
        event = self._world.begin_op(
            "inventory.held_seat", f"booking={booking_id!r}", mutating=False
        )
        seat = self._state.holds.get(booking_id)
        event.outcome = f"ok ({seat!r})"
        return seat
