"""Task 6: the worker that was only slow, not dead.

Every other task in this eval kills the process. That is the easy half of
at-least-once delivery. The hard half is that a queue cannot tell a dead
worker from a slow one, so it eventually hands the same work to a second
worker while the first is still running - and the first one wakes up and
carries on, holding everything it read before the handover.

The external system has no idempotency key and no way to query it, so a
second call means a second payout. Preventing one is not about retrying
carefully; it is about noticing that the claim you took may no longer be
yours. Concretely, a solution has to treat the result of a conditional write
as information: a `compare_and_set` that returns `False` means someone else
owns this payout now, and the only safe move is to stop without touching the
legacy system.

What makes this worth measuring is that the bug is invisible to a crash-only
test. Kill the process anywhere and claim-then-transfer behaves perfectly.
Let the process live, and the same code pays twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faultline.errors import SimulatedCrash
from faultline.faults import AttemptFault
from faultline.injector import TraceFacts
from faultline.services import DurableStore, LegacyState, LegacyTransferAPI, StoreState
from faultline.world import Event, World

TASK_ID = "t06_fenced_payout"
TITLE = "Pay out once, even when another worker takes over"
ENTRYPOINT = "send_payout"

PAYOUT_ID = "po_7741B9"
AMOUNT_CENTS = 415_000
STATE_KEY = f"payout:{PAYOUT_ID}:state"
COMPLETED = "completed"
NEEDS_REVIEW = "needs_review"

# This task adds takeover to the fault model, so it keeps the crash depth at
# one. A single crash plus a single takeover is already a four-way interleaving
# of durable state.
TAKEOVER = True
MAX_CRASHES = 1
OP_BUDGET = 64

# One remote system, reached at most twice by a correct solution.
FAULT_VARIANTS: tuple[tuple[tuple[int, str], ...], ...] = (
    (),
    ((0, "applied"),),
    ((0, "lost"),),
)


@dataclass
class Durable:
    store: StoreState = field(default_factory=StoreState)
    legacy: LegacyState = field(default_factory=LegacyState)
    # Recorded when the *second* worker fails on its own terms. Kept in durable
    # state so `check` can report it instead of it vanishing into the handover.
    takeover_error: str | None = None
    takeover_returned: Any = None
    takeover_ran: bool = False


def new_durable_state() -> Durable:
    return Durable()


def _call(world: World, solution: Any) -> Any:
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


def _run_second_worker(world: World) -> None:
    """Run a fresh worker to completion against the same durable state.

    It gets its own `World`, so it has its own operation counter and no faults
    of its own: it is the worker that the queue believes is the live one, and
    it is not interrupted. Its operations are folded into the trace so the
    counterexample reads as one story.
    """
    durable: Durable = world.durable
    durable.takeover_ran = True
    second = World(durable, AttemptFault(), world.attempt_index, world.op_budget)
    second.make_solution = world.make_solution

    try:
        durable.takeover_returned = _call(second, world.make_solution())
    except SimulatedCrash:  # pragma: no cover - the second worker has no crash point
        durable.takeover_error = "the second worker crashed"
    except Exception as exc:
        durable.takeover_error = f"{type(exc).__name__}: {exc}"

    for event in second.events:
        world.events.append(
            Event(
                op_index=event.op_index,
                kind=f"  2nd worker {event.kind}",
                detail=event.detail,
                outcome=event.outcome,
            )
        )


def invoke(world: World, solution: Any) -> Any:
    world.takeover_hook = lambda: _run_second_worker(world)
    return _call(world, solution)


def check(durable: Durable, returned: Any, facts: TraceFacts) -> list[str]:
    """Invariants.

    Note what is deliberately *not* required. When a second worker takes over,
    the two workers answer at different moments, and a worker that honestly
    reported "I could not finish this" is not wrong because the other worker
    finished it a moment later. So the only cross-worker rules are the ones
    about money and about the durable record that a human will reconcile
    from; matching a worker's answer against the final record is required
    only when nobody took over.
    """
    violations: list[str] = []
    transfers = durable.legacy.transfers
    recorded = durable.store.data.get(STATE_KEY)
    answers: list[tuple[str, Any]] = [("the first worker", returned)]
    if durable.takeover_ran and durable.takeover_error is None:
        answers.append(("the second worker", durable.takeover_returned))

    # The invariant the money depends on.
    if len(transfers) > 1:
        detail = ", ".join(f"{t.transfer_id} for {t.amount_cents}" for t in transfers)
        violations.append(
            f"the legacy system executed {len(transfers)} transfers ({detail}); at most one "
            "is acceptable under any circumstance, and a second worker taking over is not "
            "an excuse for a second payout"
        )

    if durable.takeover_error is not None:
        violations.append(
            f"the second worker raised {durable.takeover_error} instead of returning an "
            "outcome; it was handed live work and had to report something"
        )

    # Neither worker may claim success that did not happen, whenever it spoke.
    for label, answer in answers:
        if answer not in (COMPLETED, NEEDS_REVIEW):
            violations.append(
                f"{label} returned {answer!r}, expected {COMPLETED!r} or {NEEDS_REVIEW!r}"
            )
        elif answer == COMPLETED and len(transfers) != 1:
            violations.append(
                f"{label} returned {COMPLETED!r} but the legacy system executed "
                f"{len(transfers)} transfers, so the promise that the money moved exactly "
                "once is false"
            )

    # Whatever happened, the durable record has to be something a human can
    # act on, and it must not claim a payout that never went out.
    if recorded not in (COMPLETED, NEEDS_REVIEW):
        violations.append(
            f"{STATE_KEY} holds {recorded!r} after everyone finished; a payout has to end up "
            f"either {COMPLETED!r} or {NEEDS_REVIEW!r} or nobody can reconcile it"
        )
    elif recorded == COMPLETED and len(transfers) != 1:
        violations.append(
            f"{STATE_KEY} holds {COMPLETED!r} but the legacy system executed "
            f"{len(transfers)} transfers"
        )

    if not durable.takeover_ran:
        # Nobody else was involved, so the answer and the record must agree.
        if returned in (COMPLETED, NEEDS_REVIEW) and recorded != returned:
            violations.append(
                f"returned {returned!r} but {STATE_KEY} holds {recorded!r}, so the durable "
                "record disagrees with the reported outcome"
            )
        # Liveness: escalation is only honest when something actually went
        # wrong. Without this, "review everything, transfer nothing" passes.
        if facts.fault_free:
            if returned != COMPLETED:
                violations.append(
                    f"returned {returned!r} although nothing went wrong at all: no crash, no "
                    "timeout and no takeover, so the payout should simply have completed"
                )
            elif not transfers:
                violations.append("nothing went wrong, but no transfer was executed at all")

    return violations


def describe_state(durable: Durable) -> list[str]:
    lines = [durable.store.describe(), durable.legacy.describe()]
    if durable.takeover_ran:
        lines.append(f"second worker returned: {durable.takeover_returned!r}")
    return lines
