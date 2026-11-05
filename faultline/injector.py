"""Exhaustive, adaptive fault injection.

The search is adaptive rather than a blind product over a guessed operation
count: each attempt is first dry-run to discover the operations the solution
actually performs, and only the reachable crash points are then branched on.
That makes the exploration exhaustive for the declared crash depth without
wasting work on schedules that cannot occur.

Crash points are restricted to *mutating* operations plus one point after the
attempt's last operation. Crashing before a read is indistinguishable from
crashing before the following mutation, because a read leaves no durable
trace, so skipping those points loses no coverage.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .errors import GatewayTimeout, HarnessViolation, SimulatedCrash
from .faults import TIMEOUT_VARIANTS, AttemptFault, Schedule
from .world import MUTATING_OPS, Event, GatewayState, StoreState, World, _OpBudgetExceeded


# Safety valve for solutions that perform an unreasonable number of durable
# operations: without it, every extra operation adds a crash point and the
# search grows with it. Correct solutions to these tasks use well under ten.
MAX_CRASH_POINTS_PER_ATTEMPT = 32


class Task(Protocol):
    TASK_ID: str
    ENTRYPOINT: str

    def invoke(self, world: World, solution: Any) -> Any: ...

    def check(
        self, store_state: StoreState, gateway_state: GatewayState, returned: Any
    ) -> list[str]: ...


@dataclass
class AttemptResult:
    fault: AttemptFault
    events: list[Event]
    op_count: int
    mutating_indices: list[int]
    crashed: bool
    ack_lost: bool
    returned: Any = None
    error: BaseException | None = None
    swallowed_crash: bool = False

    def render(self, number: int) -> str:
        description = self.fault.describe(ack_lost=self.ack_lost)
        lines = [f"  attempt {number} ({description}):"]
        lines.extend(event.render() for event in self.events)
        if self.ack_lost:
            lines.append("    -- work finished, then the process died before acknowledging")
        elif self.crashed:
            lines.append("    -- process died here; the queue will redeliver")
        elif self.error is not None:
            lines.append(f"    -- handler raised {type(self.error).__name__}: {self.error}")
        else:
            lines.append(f"    -- handler returned {self.returned!r}")
        return "\n".join(lines)


@dataclass
class TraceResult:
    attempts: tuple[AttemptResult, ...]
    store_state: StoreState
    gateway_state: GatewayState
    violations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    @property
    def schedule(self) -> Schedule:
        return Schedule(tuple(a.fault for a in self.attempts))

    def render(self) -> str:
        lines = [f"trace with {len(self.attempts)} attempt(s):"]
        lines.extend(a.render(i) for i, a in enumerate(self.attempts, start=1))
        lines.append("  final durable store: " + repr(self.store_state.data))
        charges = self.gateway_state.charge_list()
        lines.append(
            "  charges on the gateway: "
            + (
                ", ".join(f"{c.charge_id}({c.amount_cents}, key={c.idempotency_key})" for c in charges)
                or "none"
            )
        )
        for violation in self.violations:
            lines.append(f"  VIOLATION: {violation}")
        return "\n".join(lines)


@dataclass
class EvalResult:
    task_id: str
    traces_run: int
    failures: list[TraceResult]
    budget_exhausted: bool = False
    crash_points_truncated: bool = False
    load_error: str | None = None

    @property
    def passed(self) -> bool:
        return self.load_error is None and not self.failures

    def minimal_counterexample(self) -> TraceResult | None:
        """Smallest failing trace: fewest attempts, then fewest operations.

        Reporting the smallest witness keeps the explanation of *why* a
        solution is wrong as short as possible.
        """
        if not self.failures:
            return None
        return min(
            self.failures,
            key=lambda t: (len(t.attempts), sum(a.op_count for a in t.attempts)),
        )


def _run_attempt(
    task: Task,
    make_solution: Callable[[], Any],
    store_state: StoreState,
    gateway_state: GatewayState,
    fault: AttemptFault,
    attempt_index: int,
    op_budget: int,
) -> AttemptResult:
    world = World(store_state, gateway_state, fault, attempt_index, op_budget)
    crashed = False
    ack_lost = False
    returned: Any = None
    error: BaseException | None = None
    swallowed = False

    try:
        # Fresh module namespace: the previous attempt's process is gone.
        returned = task.invoke(world, make_solution())
    except _OpBudgetExceeded as exc:
        error = exc
    except SimulatedCrash:
        crashed = True
    except Exception as exc:
        # Includes GatewayTimeout: letting an expected, documented condition
        # escape the handler is itself a failure.
        error = exc
    else:
        if world.crash_raised:
            # Solution code caught the crash instead of dying. A real process
            # cannot do that, so this is a harness violation, not a pass.
            swallowed = True
            error = HarnessViolation(
                "solution code caught SimulatedCrash; a killed process cannot continue"
            )
        elif fault.crash_before_op is not None:
            # The crash point was past the final operation: the handler did all
            # of its work and then died before acknowledging, so the queue
            # redelivers regardless.
            crashed = True
            ack_lost = True

    return AttemptResult(
        fault=fault,
        events=world.events,
        op_count=world.op_index,
        mutating_indices=[e.op_index for e in world.events if e.kind in MUTATING_OPS],
        crashed=crashed,
        ack_lost=ack_lost,
        returned=returned,
        error=error,
        swallowed_crash=swallowed,
    )


def _violations(
    task: Task, store: StoreState, gateway: GatewayState, final: AttemptResult
) -> list[str]:
    if isinstance(final.error, _OpBudgetExceeded):
        return [f"the handler never finished: {final.error}"]
    if final.swallowed_crash:
        return [str(final.error)]
    if final.error is not None:
        return [
            f"the handler raised {type(final.error).__name__} on an attempt that was "
            f"allowed to complete: {final.error}"
        ]
    return task.check(store, gateway, final.returned)


def run_schedule(
    task: Task,
    make_solution: Callable[[], Any],
    schedule: Schedule,
    op_budget: int = 64,
) -> TraceResult:
    """Run one specific fault schedule. Used by the public self-check and to
    replay a counterexample on demand."""
    store, gateway = StoreState(), GatewayState()
    attempts: list[AttemptResult] = []
    for index, fault in enumerate(schedule.attempts, start=1):
        attempts.append(
            _run_attempt(task, make_solution, store, gateway, fault, index, op_budget)
        )
    trace = TraceResult(tuple(attempts), store, gateway)
    trace.violations = _violations(task, store, gateway, attempts[-1])
    return trace


def _trace_signature(attempts: tuple[AttemptResult, ...]) -> tuple:
    """Canonical identity of a trace, used to drop schedules that differ on
    paper but produce an identical execution (for example a timeout aimed at a
    charge call the solution never makes)."""
    return tuple(
        (i, e.kind, e.detail, e.outcome)
        for i, attempt in enumerate(attempts)
        for e in attempt.events
    ) + tuple(
        (i, attempt.crashed, attempt.ack_lost, repr(attempt.returned), type(attempt.error).__name__)
        for i, attempt in enumerate(attempts)
    )


def explore(
    task: Task,
    make_solution: Callable[[], Any],
    max_crashes: int = 2,
    op_budget: int = 64,
    trace_budget: int = 20000,
) -> EvalResult:
    """Run the solution through every fault schedule up to `max_crashes` crashes."""
    failures: list[TraceResult] = []
    seen: set[tuple] = set()
    counters: dict[str, Any] = {"traces": 0, "exhausted": False, "truncated": False}

    def record(attempts: tuple[AttemptResult, ...], store: StoreState, gateway: GatewayState) -> None:
        signature = _trace_signature(attempts)
        if signature in seen:
            return
        seen.add(signature)
        counters["traces"] += 1

        violations = _violations(task, store, gateway, attempts[-1])
        if violations:
            failures.append(TraceResult(attempts, store, gateway, violations))

    def recurse(
        store_state: StoreState,
        gateway_state: GatewayState,
        history: tuple[AttemptResult, ...],
        crashes_left: int,
    ) -> None:
        if counters["exhausted"]:
            return

        for timeouts in TIMEOUT_VARIANTS:
            store, gateway = copy.deepcopy(store_state), copy.deepcopy(gateway_state)
            fault = AttemptFault(crash_before_op=None, charge_timeouts=timeouts)
            result = _run_attempt(
                task, make_solution, store, gateway, fault, len(history) + 1, op_budget
            )
            record(history + (result,), store, gateway)
            if counters["traces"] >= trace_budget:
                counters["exhausted"] = True
                return

        if crashes_left == 0:
            return

        for timeouts in TIMEOUT_VARIANTS:
            probe_store, probe_gateway = copy.deepcopy(store_state), copy.deepcopy(gateway_state)
            probe = _run_attempt(
                task,
                make_solution,
                probe_store,
                probe_gateway,
                AttemptFault(crash_before_op=None, charge_timeouts=timeouts),
                len(history) + 1,
                op_budget,
            )
            if isinstance(probe.error, _OpBudgetExceeded):
                # A runaway solution would otherwise contribute one crash point
                # per spin. It has already been recorded as a failure by the
                # terminal loop above, so stop descending into it.
                continue

            crash_points = [*probe.mutating_indices, probe.op_count]
            if len(crash_points) > MAX_CRASH_POINTS_PER_ATTEMPT:
                counters["truncated"] = True
                crash_points = crash_points[:MAX_CRASH_POINTS_PER_ATTEMPT]

            for point in crash_points:
                store, gateway = copy.deepcopy(store_state), copy.deepcopy(gateway_state)
                fault = AttemptFault(crash_before_op=point, charge_timeouts=timeouts)
                result = _run_attempt(
                    task, make_solution, store, gateway, fault, len(history) + 1, op_budget
                )
                if result.swallowed_crash:
                    # The solution caught the crash and carried on instead of
                    # dying. There is no next attempt to descend into, and it
                    # must not be silently dropped either.
                    record(history + (result,), store, gateway)
                    continue
                if not result.crashed:
                    continue
                recurse(store, gateway, history + (result,), crashes_left - 1)
                if counters["exhausted"]:
                    return

    recurse(StoreState(), GatewayState(), (), max_crashes)

    return EvalResult(
        task_id=task.TASK_ID,
        traces_run=counters["traces"],
        failures=failures,
        budget_exhausted=counters["exhausted"],
        crash_points_truncated=counters["truncated"],
    )
