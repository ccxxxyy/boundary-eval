"""The deterministic world that solution code runs against.

There is no wall clock, no real network and no real filesystem, so a trace that
fails once fails identically forever and can be replayed as a counterexample.

State is split into what survives a crash and what does not. Each task defines
a *durable state* object holding everything that outlives the process - stored
records, charges accepted by a payment provider, messages a broker has already
taken - and that object is carried from one attempt to the next. A `World` is
per-attempt scratch state and is thrown away on every crash, which is what
makes in-memory bookkeeping in solution code unsafe.

Services (`faultline.services`) are thin facades that read and write durable
state through `World.begin_op`, so every durable operation becomes a candidate
crash point and every remote call becomes a candidate timeout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import SimulatedCrash
from .faults import AttemptFault


@dataclass
class Event:
    op_index: int
    kind: str
    detail: str
    outcome: str = "ok"

    def render(self) -> str:
        suffix = "" if self.outcome == "ok" else f"  -> {self.outcome}"
        return f"    #{self.op_index:<2} {self.kind:<22} {self.detail}{suffix}"


class OpBudgetExceeded(SimulatedCrash):
    """Solution code performed an unreasonable number of operations, almost
    always a runaway loop. Reported separately from an invariant violation."""


class World:
    """One attempt's view of the world.

    `fault` says what goes wrong during this attempt and comes from the
    injector, never from solution code.
    """

    def __init__(
        self,
        durable: Any,
        fault: AttemptFault,
        attempt_index: int,
        op_budget: int = 64,
    ) -> None:
        self.durable = durable
        self.fault = fault
        self.attempt_index = attempt_index
        self.op_budget = op_budget

        self.op_index = 0
        self.remote_calls = 0
        self.id_calls = 0
        self.events: list[Event] = []
        self.mutating_indices: list[int] = []
        self.crash_raised = False

        # Set by a task that models takeover. Called at most once, immediately
        # before the operation named by `fault.takeover_before_op`, and
        # expected to run a second worker to completion against the same
        # durable state.
        self.takeover_hook: Any = None
        self.takeover_ran = False

        # Set by the injector so a task that models takeover can build a
        # second, independent worker from the same solution source.
        self.make_solution: Any = None

    def begin_op(self, kind: str, detail: str, mutating: bool) -> Event:
        """Open a durable or remote operation.

        Crash points are placed before *mutating* operations only. Crashing
        before a read is indistinguishable from crashing before the next write,
        because a read leaves no durable trace, so those points would add
        traces without adding coverage.
        """
        if self.op_index >= self.op_budget:
            raise OpBudgetExceeded(f"more than {self.op_budget} operations without finishing")

        if (
            self.takeover_hook is not None
            and not self.takeover_ran
            and self.fault.takeover_before_op == self.op_index
        ):
            # This worker is merely slow, not dead. Another one is handed the
            # same work, runs it to completion, and then this one resumes.
            self.takeover_ran = True
            self.events.append(
                Event(
                    op_index=self.op_index,
                    kind="-- TAKEOVER --",
                    detail="the queue hands this work to a second worker",
                    outcome="the second worker runs to completion below",
                )
            )
            self.takeover_hook()
            self.events.append(
                Event(
                    op_index=self.op_index,
                    kind="-- RESUMES --",
                    detail="the first worker was only slow, and now continues",
                    outcome="",
                )
            )

        event = Event(op_index=self.op_index, kind=kind, detail=detail)
        self.events.append(event)
        if mutating:
            self.mutating_indices.append(self.op_index)

        if mutating and self.fault.crash_before_op == self.op_index:
            event.outcome = "CRASH (operation never applied)"
            self.op_index += 1
            self.crash_raised = True
            raise SimulatedCrash(f"crash before op #{event.op_index} ({kind})")

        self.op_index += 1
        return event

    def next_remote_call(self) -> int:
        """Claim the index of a remote call, which is how timeout faults are
        addressed. Shared across services so a task using two remote systems
        still has a single, well-ordered fault axis."""
        index = self.remote_calls
        self.remote_calls += 1
        return index

    def new_id(self) -> str:
        """A fresh identifier, as `uuid4().hex` would be: never repeated, and
        not reproducible after a restart."""
        self.id_calls += 1
        return f"id-a{self.attempt_index}-{self.id_calls}"
