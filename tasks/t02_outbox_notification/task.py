"""Task 2: the outbox problem, with no shortcut.

Two systems have to agree and there is no transaction spanning them. The
interesting part is that both directions are failures: publishing before the
state is durable lets a consumer read back an order that has not shipped, and
treating "already shipped" as "already notified" loses the notification
entirely when the process dies between the two.

That second one is the trap worth measuring. The obvious idempotency guard -
return early if the order is already marked shipped - is exactly wrong here,
and it looks like good defensive code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faultline.services import BusState, DurableStore, EventBus, StoreState
from faultline.world import World

TASK_ID = "t02_outbox_notification"
TITLE = "Ship an order and notify downstream exactly once"
ENTRYPOINT = "mark_shipped"

ORDER_ID = "ord_20B4C7"
STATUS_KEY = f"order:{ORDER_ID}:status"
SHIPPED = "shipped"
PAYLOAD = f"order_shipped:{ORDER_ID}"

MAX_CRASHES = 2
OP_BUDGET = 64


@dataclass
class Durable:
    store: StoreState = field(default_factory=StoreState)
    bus: BusState = field(default_factory=BusState)


def new_durable_state() -> Durable:
    return Durable()


def invoke(world: World, solution: Any) -> Any:
    handler = getattr(solution, ENTRYPOINT, None)
    if handler is None:
        raise AttributeError(f"solution does not define {ENTRYPOINT}()")
    durable: Durable = world.durable
    return handler(
        order_id=ORDER_ID,
        store=DurableStore(world, durable.store),
        bus=EventBus(world, durable.bus, durable.store),
        new_id=world.new_id,
    )


def check(durable: Durable, returned: Any) -> list[str]:
    violations: list[str] = []

    status = durable.store.data.get(STATUS_KEY)
    if status != SHIPPED:
        violations.append(
            f"{STATUS_KEY} holds {status!r}, expected {SHIPPED!r}: the order is not recorded "
            "as shipped"
        )

    notifications = durable.bus.with_payload(PAYLOAD)
    if not notifications:
        violations.append(
            "no notification was delivered: the order shipped and nothing downstream was told"
        )
    else:
        event_ids = sorted({event.event_id for event in notifications})
        if len(event_ids) > 1:
            violations.append(
                f"the notification was delivered under {len(event_ids)} different event ids "
                f"({', '.join(repr(e) for e in event_ids)}), so the consumer acts on it "
                f"{len(event_ids)} times"
            )

        premature = [
            event
            for event in notifications
            if event.store_at_publish.get(STATUS_KEY) != SHIPPED
        ]
        if premature:
            first = premature[0]
            violations.append(
                f"message #{first.sequence} was published while {STATUS_KEY} held "
                f"{first.store_at_publish.get(STATUS_KEY)!r}: a consumer reading the order "
                "back would not find it shipped"
            )

    return violations


def describe_state(durable: Durable) -> list[str]:
    return [durable.store.describe(), durable.bus.describe()]
