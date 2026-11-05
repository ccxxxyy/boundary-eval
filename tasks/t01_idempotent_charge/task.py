"""Task 1: charge a customer exactly once across crashes and ambiguous timeouts.

The limitation under test is *claim before you act*. The idempotency key has to
be chosen and durably recorded before the charge is attempted, because a key
held only in memory is regenerated after a crash and buys a second charge. The
happy path works either way, which is what makes the bug survive review.
"""

from __future__ import annotations

from typing import Any

from faultline.world import GatewayState, StoreState, World

TASK_ID = "t01_idempotent_charge"
TITLE = "Charge a customer exactly once"
ENTRYPOINT = "handle_order"

ORDER_ID = "ord_7F3A91"
AMOUNT_CENTS = 4999

MAX_CRASHES = 2
OP_BUDGET = 64


def invoke(world: World, solution: Any) -> Any:
    handler = getattr(solution, ENTRYPOINT, None)
    if handler is None:
        raise AttributeError(f"solution does not define {ENTRYPOINT}()")
    return handler(
        order_id=ORDER_ID,
        amount_cents=AMOUNT_CENTS,
        store=world.store,
        gateway=world.gateway,
        new_id=world.new_id,
    )


def check(store_state: StoreState, gateway_state: GatewayState, returned: Any) -> list[str]:
    violations: list[str] = []
    charges = gateway_state.charge_list()

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
            violations.append(
                f"charged {charge.amount_cents} cents instead of {AMOUNT_CENTS}"
            )
        if returned != charge.charge_id:
            violations.append(
                f"handler returned {returned!r} but the only charge on the gateway is "
                f"{charge.charge_id!r}"
            )

    return violations
