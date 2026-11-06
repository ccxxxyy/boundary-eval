"""Task 5: a two-system saga, where the compensation is the hard part.

Reserving the seat is made easy on purpose - both inventory operations are
idempotent and keyed by the booking - so the task is entirely about what
happens when the charge does not go the easy way.

Two failures matter here and they pull in opposite directions. Recording
"declined" before the seat is actually released leaks the seat forever, because
the redelivery sees a terminal state and returns. Treating an ambiguous
gateway timeout as a decline releases a seat the customer has already paid
for. Getting both right means recognising that "I don't know" is a third
answer, and that the gateway can be asked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faultline.injector import TraceFacts
from faultline.services import (
    DurableStore,
    GatewayState,
    InventoryState,
    PaymentGateway,
    SeatInventory,
    StoreState,
)
from faultline.world import World

TASK_ID = "t05_saga_compensation"
TITLE = "Book a seat, or give it back"
ENTRYPOINT = "book_seat"

BOOKING_ID = "bk_9C41"
SEAT = "14C"
AMOUNT_CENTS = 18_500
CONFIRMED = "confirmed"
DECLINED = "declined"

MAX_CRASHES = 2
OP_BUDGET = 64

# This task's prompt lists a definite decline alongside the timeouts, so its
# fault model is wider than the default. Declines are aimed at the first two
# remote calls because which one is the charge depends on the solution's order;
# services ignore fault kinds that do not apply to them.
FAULT_VARIANTS: tuple[tuple[tuple[int, str], ...], ...] = (
    (),
    ((0, "declined"),),
    ((1, "declined"),),
    ((0, "applied"),),
    ((0, "lost"),),
    ((1, "applied"),),
    ((1, "lost"),),
    ((2, "applied"),),
    ((2, "lost"),),
)


@dataclass
class Durable:
    store: StoreState = field(default_factory=StoreState)
    inventory: InventoryState = field(default_factory=InventoryState)
    gateway: GatewayState = field(default_factory=GatewayState)


def new_durable_state() -> Durable:
    return Durable()


def invoke(world: World, solution: Any) -> Any:
    handler = getattr(solution, ENTRYPOINT, None)
    if handler is None:
        raise AttributeError(f"solution does not define {ENTRYPOINT}()")
    durable: Durable = world.durable
    return handler(
        booking_id=BOOKING_ID,
        seat=SEAT,
        amount_cents=AMOUNT_CENTS,
        store=DurableStore(world, durable.store),
        inventory=SeatInventory(world, durable.inventory),
        gateway=PaymentGateway(world, durable.gateway),
        new_id=world.new_id,
    )


def check(durable: Durable, returned: Any, facts: TraceFacts) -> list[str]:
    violations: list[str] = []
    charges = durable.gateway.charge_list()
    held = durable.inventory.holds.get(BOOKING_ID)

    if len(charges) > 1:
        detail = ", ".join(f"{c.charge_id} for {c.amount_cents}" for c in charges)
        violations.append(f"the customer was charged {len(charges)} times: {detail}")

    if charges and held is None:
        violations.append(
            f"{charges[0].charge_id} took {charges[0].amount_cents} from the customer but the "
            "booking holds no seat: they paid for nothing"
        )

    if returned == CONFIRMED:
        if len(charges) != 1:
            violations.append(
                f"returned {CONFIRMED!r} but {len(charges)} charges exist"
            )
        elif charges[0].amount_cents != AMOUNT_CENTS:
            violations.append(
                f"returned {CONFIRMED!r} but the charge is for {charges[0].amount_cents}, "
                f"not {AMOUNT_CENTS}"
            )
        if held != SEAT:
            violations.append(
                f"returned {CONFIRMED!r} but the booking holds {held!r}, not {SEAT!r}"
            )
    elif returned == DECLINED:
        if charges:
            violations.append(
                f"returned {DECLINED!r} but {charges[0].charge_id} exists, so money was taken"
            )
        if held is not None:
            violations.append(
                f"returned {DECLINED!r} but the booking still holds {held!r}: that seat can "
                "never be sold again"
            )
        if facts.fault_free:
            violations.append(
                f"returned {DECLINED!r} although nothing went wrong: no crash, no timeout and "
                "no decline occurred"
            )
    else:
        violations.append(f"returned {returned!r}, expected {CONFIRMED!r} or {DECLINED!r}")

    if facts.declined_cleanly and returned != DECLINED:
        violations.append(
            f"the gateway gave a definite decline and nothing else went wrong, but the result "
            f"was {returned!r}"
        )

    return violations


def describe_state(durable: Durable) -> list[str]:
    return [
        durable.store.describe(),
        durable.inventory.describe(),
        durable.gateway.describe(),
    ]
