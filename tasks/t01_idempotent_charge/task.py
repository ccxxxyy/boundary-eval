"""Task 1: charge a customer exactly once across crashes and ambiguous timeouts.

The limitation under test is *claim before you act*. The idempotency key has to
be fixed and durable before the charge is attempted, because a key held only in
memory is regenerated after a crash and buys a second charge. The happy path
works either way, which is what makes the bug survive review.

This is also the eval's calibration task: a solution that derives the key from
the order id is correct and simple, so a model with the right instinct passes.
It discriminates between two implementations that are both common, rather than
between right and ridiculous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faultline.services import DurableStore, GatewayState, PaymentGateway, StoreState
from faultline.world import World

TASK_ID = "t01_idempotent_charge"
TITLE = "Charge a customer exactly once"
ENTRYPOINT = "handle_order"

ORDER_ID = "ord_7F3A91"
AMOUNT_CENTS = 4999

MAX_CRASHES = 2
OP_BUDGET = 64


@dataclass
class Durable:
    store: StoreState = field(default_factory=StoreState)
    gateway: GatewayState = field(default_factory=GatewayState)


def new_durable_state() -> Durable:
    return Durable()


def invoke(world: World, solution: Any) -> Any:
    handler = getattr(solution, ENTRYPOINT, None)
    if handler is None:
        raise AttributeError(f"solution does not define {ENTRYPOINT}()")
    durable: Durable = world.durable
    return handler(
        order_id=ORDER_ID,
        amount_cents=AMOUNT_CENTS,
        store=DurableStore(world, durable.store),
        gateway=PaymentGateway(world, durable.gateway),
        new_id=world.new_id,
    )


def check(durable: Durable, returned: Any) -> list[str]:
    violations: list[str] = []
    charges = durable.gateway.charge_list()

    if not charges:
        violations.append("the customer was never charged (expected exactly one charge)")
    elif len(charges) > 1:
        detail = ", ".join(
            f"{c.charge_id} for {c.amount_cents} under key {c.idempotency_key!r}" for c in charges
        )
        violations.append(
            f"the customer was charged {len(charges)} times (expected exactly one): {detail}"
        )
    else:
        charge = charges[0]
        if charge.amount_cents != AMOUNT_CENTS:
            violations.append(f"charged {charge.amount_cents} cents instead of {AMOUNT_CENTS}")
        if returned != charge.charge_id:
            violations.append(
                f"handler returned {returned!r} but the only charge on the gateway is "
                f"{charge.charge_id!r}"
            )

    return violations


def describe_state(durable: Durable) -> list[str]:
    return [durable.store.describe(), durable.gateway.describe()]
