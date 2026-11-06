"""Description of what goes wrong during a single attempt, and during a trace.

A *trace* is a sequence of attempts. The queue redelivers the work after every
crash, so attempt N+1 starts from whatever durable state attempt N left behind.
The final attempt of every trace always runs to completion, which is when the
invariants are checked.
"""

from __future__ import annotations

from dataclasses import dataclass

# What can happen to an individual remote call within one attempt.
#   None       - the call succeeds normally
#   "lost"     - times out and the request was NOT applied
#   "applied"  - times out but the request WAS applied (the ambiguous outcome)
#   "declined" - a definite business refusal; nothing was applied and
#                retrying will not change the answer
TimeoutKind = str

# The default fault model: timeouts only. A task whose prompt lists other
# outcomes declares its own `FAULT_VARIANTS`, so the faults a solution is
# graded against are exactly the ones its prompt disclosed.
TIMEOUT_VARIANTS: tuple[tuple[tuple[int, TimeoutKind], ...], ...] = (
    (),                      # nothing goes wrong
    ((0, "applied"),),       # first remote call: ambiguous timeout
    ((0, "lost"),),          # first remote call: clean timeout
    ((1, "applied"),),       # second remote call: ambiguous timeout
    ((1, "lost"),),          # second remote call: clean timeout
)


@dataclass(frozen=True)
class AttemptFault:
    """Faults applied to one attempt.

    `crash_before_op` is an index into the attempt's operation sequence. The
    operation at that index never takes effect and the process dies. A value
    equal to the attempt's total operation count means the attempt finished its
    work but died before acknowledging, so the queue redelivers anyway.
    """

    crash_before_op: int | None = None
    remote_timeouts: tuple[tuple[int, TimeoutKind], ...] = ()

    def timeout_for(self, remote_call_index: int) -> TimeoutKind | None:
        for index, kind in self.remote_timeouts:
            if index == remote_call_index:
                return kind
        return None

    def describe(self, ack_lost: bool = False) -> str:
        parts = []
        if self.crash_before_op is None:
            parts.append("runs to completion")
        elif ack_lost:
            parts.append("dies after its last operation, before acknowledging")
        else:
            parts.append(f"crashes before op #{self.crash_before_op}")
        labels = {
            "applied": "timeout, but the request WAS applied",
            "lost": "timeout, the request was not applied",
            "declined": "declined",
        }
        for index, kind in self.remote_timeouts:
            parts.append(f"remote call #{index}: {labels.get(kind, kind)}")
        return "; ".join(parts)


@dataclass(frozen=True)
class Schedule:
    """A full trace: one `AttemptFault` per attempt, last one non-crashing."""

    attempts: tuple[AttemptFault, ...]

    def describe(self) -> str:
        lines = []
        for i, fault in enumerate(self.attempts, start=1):
            lines.append(f"  attempt {i}: {fault.describe()}")
        return "\n".join(lines)
