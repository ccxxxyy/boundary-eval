"""Task 3: at-least-once delivery, no multi-key transaction, bounded state.

The deduplication marker and the balance it guards are two separate facts, the
store has no multi-key transaction, and so *neither* order works: marking first
loses the amount if the process dies in between, applying first double-counts
it on redelivery.

The only way through is to stop treating them as two facts - to make the write
that records "this message is accounted for" the same write that accounts for
it.

The store caps one value at `MAX_VALUE_BYTES`, which rules out the degenerate
answer of serialising the balance and every message id ever seen into a single
key. That answer is crash-safe only because it makes a single-key store
transactional, and it is a real bug: the row grows forever. With the cap, a
solution has to carry at most one message's worth of in-flight information in
any single value, which is where the task gets interesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faultline.services import DurableStore, StoreState
from faultline.injector import TraceFacts
from faultline.world import World

TASK_ID = "t03_at_least_once_ledger"
TITLE = "Apply each ledger message exactly once, with bounded durable state"
ENTRYPOINT = "handle_message"

# One value holds a balance plus at most one message id comfortably; it cannot
# hold the balance plus all six.
MAX_VALUE_BYTES = 32

# The same batch the prompt shows, duplicates included.
BATCH: tuple[tuple[str, int], ...] = (
    ("m_payroll", 250_000),
    ("m_rent", -90_000),
    ("m_payroll", 250_000),
    ("m_refund", 12_500),
    ("m_bonus", 40_000),
    ("m_rent", -90_000),
    ("m_fees", -1_500),
    ("m_tax", -33_000),
    ("m_bonus", 40_000),
    ("m_tax", -33_000),
)
EXPECTED_BALANCE = sum(dict(BATCH).values())

# No remote systems in this task, so there is nothing for a timeout to hit.
# Declaring the fault model explicitly keeps the public self-check honest
# instead of listing outcomes that can never occur.
FAULT_VARIANTS: tuple[tuple[tuple[int, str], ...], ...] = ((),)

MAX_CRASHES = 2
OP_BUDGET = 400


@dataclass
class Durable:
    store: StoreState = field(
        default_factory=lambda: StoreState(max_value_bytes=MAX_VALUE_BYTES)
    )


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


def check(durable: Durable, returned: Any, facts: TraceFacts) -> list[str]:
    if not isinstance(returned, int) or isinstance(returned, bool):
        return [f"read_balance() returned {returned!r}, expected an int"]

    oversized = [
        (key, value)
        for key, value in durable.store.data.items()
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES
    ]
    if oversized:
        key, value = oversized[0]
        return [
            f"key {key!r} holds {len(value.encode('utf-8'))} bytes, over the "
            f"{MAX_VALUE_BYTES}-byte limit"
        ]

    if returned != EXPECTED_BALANCE:
        difference = returned - EXPECTED_BALANCE
        amounts = dict(BATCH)
        detail = ""
        twice = [m for m, a in amounts.items() if a == difference]
        lost = [m for m, a in amounts.items() if -a == difference]
        if twice:
            detail = f" ({twice[0]} looks applied one time too many)"
        elif lost:
            detail = f" ({lost[0]} looks lost)"
        return [
            f"balance is {returned}, expected {EXPECTED_BALANCE}, off by "
            f"{difference:+d}{detail}"
        ]
    return []


def describe_state(durable: Durable) -> list[str]:
    return [durable.store.describe(), f"expected balance: {EXPECTED_BALANCE}"]
