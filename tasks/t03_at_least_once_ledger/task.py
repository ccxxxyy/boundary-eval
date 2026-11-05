"""Task 3: at-least-once delivery with no multi-key transaction.

This is the task with no shortcut. The deduplication marker and the balance it
guards are two separate facts, the store has no multi-key transaction, and so
*neither* order works: marking first loses the amount if the process dies in
between, applying first double-counts it on redelivery.

The only way through is to stop treating them as two facts - to keep the
dedup state and the data it guards in a single atomic write, whether that is
one composite record or one key per message. A model that has internalised why
multi-key atomicity matters finds that; a model pattern-matching on
"idempotent consumer" writes one of the two broken orderings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faultline.services import DurableStore, StoreState
from faultline.world import World

TASK_ID = "t03_at_least_once_ledger"
TITLE = "Apply each ledger message exactly once"
ENTRYPOINT = "handle_message"

# The same batch the prompt shows, duplicates included.
BATCH: tuple[tuple[str, int], ...] = (
    ("m_payroll", 250_000),
    ("m_rent", -90_000),
    ("m_payroll", 250_000),
    ("m_refund", 12_500),
    ("m_rent", -90_000),
)
EXPECTED_BALANCE = sum(dict(BATCH).values())

MAX_CRASHES = 2
OP_BUDGET = 96


@dataclass
class Durable:
    store: StoreState = field(default_factory=StoreState)


def new_durable_state() -> Durable:
    return Durable()


def invoke(world: World, solution: Any) -> Any:
    handler = getattr(solution, ENTRYPOINT, None)
    if handler is None:
        raise AttributeError(f"solution does not define {ENTRYPOINT}()")
    reader = getattr(solution, "read_balance", None)
    if reader is None:
        raise AttributeError("solution does not define read_balance()")

    durable: Durable = world.durable
    store = DurableStore(world, durable.store)
    for message_id, amount_cents in BATCH:
        handler(message_id=message_id, amount_cents=amount_cents, store=store)
    return reader(store=store)


def check(durable: Durable, returned: Any) -> list[str]:
    if not isinstance(returned, int) or isinstance(returned, bool):
        return [f"read_balance() returned {returned!r}, expected an int"]
    if returned != EXPECTED_BALANCE:
        difference = returned - EXPECTED_BALANCE
        applied_twice = [
            message_id
            for message_id, amount in dict(BATCH).items()
            if amount == difference
        ]
        detail = ""
        if applied_twice:
            detail = f" ({applied_twice[0]} looks applied one time too many)"
        elif any(-amount == difference for amount in dict(BATCH).values()):
            lost = [m for m, a in dict(BATCH).items() if -a == difference]
            detail = f" ({lost[0]} looks lost)"
        return [
            f"balance is {returned}, expected {EXPECTED_BALANCE}, off by "
            f"{difference:+d}{detail}"
        ]
    return []


def describe_state(durable: Durable) -> list[str]:
    return [durable.store.describe(), f"expected balance: {EXPECTED_BALANCE}"]
