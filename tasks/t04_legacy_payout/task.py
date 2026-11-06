"""Task 4: when exactly-once is not available, say so.

Against a system with no idempotency key and no way to query it, exactly-once
delivery is not a goal that better code can reach. The engineering answer is
at-most-once plus an honest report when the outcome is unknown, so a person can
reconcile it.

Models tend to reach for the retry loop anyway, because retrying is what the
training data does when a call fails. Here the retry is the bug, and it costs a
supplier a second payout.

The liveness clause matters as much as the safety one: escalating is only
allowed when something actually went wrong, otherwise "review everything and
transfer nothing" would be a passing solution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faultline.injector import TraceFacts
from faultline.services import DurableStore, LegacyState, LegacyTransferAPI, StoreState
from faultline.world import World

TASK_ID = "t04_legacy_payout"
TITLE = "Pay out through a legacy system at most once"
ENTRYPOINT = "send_payout"

PAYOUT_ID = "po_5513E2"
AMOUNT_CENTS = 820_000
STATE_KEY = f"payout:{PAYOUT_ID}:state"
COMPLETED = "completed"
NEEDS_REVIEW = "needs_review"

MAX_CRASHES = 2
OP_BUDGET = 64


@dataclass
class Durable:
    store: StoreState = field(default_factory=StoreState)
    legacy: LegacyState = field(default_factory=LegacyState)


def new_durable_state() -> Durable:
    return Durable()


def invoke(world: World, solution: Any) -> Any:
    handler = getattr(solution, ENTRYPOINT, None)
    if handler is None:
        raise AttributeError(f"solution does not define {ENTRYPOINT}()")
    durable: Durable = world.durable
    return handler(
        payout_id=PAYOUT_ID,
        amount_cents=AMOUNT_CENTS,
        store=DurableStore(world, durable.store),
        legacy=LegacyTransferAPI(world, durable.legacy),
        new_id=world.new_id,
    )


def check(durable: Durable, returned: Any, facts: TraceFacts) -> list[str]:
    violations: list[str] = []
    transfers = durable.legacy.transfers
    recorded = durable.store.data.get(STATE_KEY)

    if len(transfers) > 1:
        detail = ", ".join(f"{t.transfer_id} for {t.amount_cents}" for t in transfers)
        violations.append(
            f"the legacy system executed {len(transfers)} transfers ({detail}); at most one "
            "is acceptable under any circumstance"
        )

    if returned == COMPLETED:
        if len(transfers) != 1:
            violations.append(
                f"returned {COMPLETED!r} but {len(transfers)} transfers were executed, so the "
                "promise that the money moved exactly once is false"
            )
        if recorded != COMPLETED:
            violations.append(
                f"returned {COMPLETED!r} but {STATE_KEY} holds {recorded!r}, so the durable "
                "record disagrees with the reported outcome"
            )
    elif returned == NEEDS_REVIEW:
        if recorded != NEEDS_REVIEW:
            violations.append(
                f"returned {NEEDS_REVIEW!r} but {STATE_KEY} holds {recorded!r}, so nobody "
                "will ever find this payout to reconcile it"
            )
        if facts.fault_free:
            violations.append(
                f"returned {NEEDS_REVIEW!r} although nothing went wrong: no crash and no "
                "timeout occurred, so the payout should simply have completed"
            )
    else:
        violations.append(
            f"returned {returned!r}, expected {COMPLETED!r} or {NEEDS_REVIEW!r}"
        )

    return violations


def describe_state(durable: Durable) -> list[str]:
    return [durable.store.describe(), durable.legacy.describe()]
