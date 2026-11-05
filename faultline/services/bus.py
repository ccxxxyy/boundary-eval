"""A message broker with at-least-once delivery.

It does **not** deduplicate. Every publish it accepts is delivered downstream,
duplicates included, which is what real brokers mostly do and what makes the
outbox pattern necessary in the first place. Exactly-once publishing is not
available here; the achievable goal is at-least-once with a stable event id so
that consumers can deduplicate.

Each accepted publish also records the durable state as it was at that instant.
Solution code cannot see that snapshot - it exists so the grader can state
"this message was published while the order was not yet durably shipped",
which is a claim about ordering that final state alone cannot support.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import BrokerTimeout
from ..world import World
from .store import StoreState


@dataclass
class PublishedEvent:
    sequence: int
    event_id: str
    payload: str
    store_at_publish: dict[str, str]


@dataclass
class BusState:
    published: list[PublishedEvent] = field(default_factory=list)

    def with_payload(self, payload: str) -> list[PublishedEvent]:
        return [event for event in self.published if event.payload == payload]

    def describe(self) -> str:
        if not self.published:
            return "messages delivered downstream: none"
        rendered = ", ".join(
            f"#{e.sequence}({e.payload}, event_id={e.event_id})" for e in self.published
        )
        return f"messages delivered downstream: {rendered}"


class EventBus:
    def __init__(self, world: World, state: BusState, store_state: StoreState) -> None:
        self._world = world
        self._state = state
        self._store_state = store_state

    def publish(self, event_id: str, payload: str) -> None:
        """Hand a message to the broker for delivery.

        The broker does not deduplicate: consumers see every message it
        accepts. May raise `BrokerTimeout`, in which case the message may or
        may not have been accepted.
        """
        world = self._world
        call_index = world.next_remote_call()
        event = world.begin_op(
            "bus.publish", f"event_id={event_id!r} payload={payload!r}", mutating=True
        )
        timeout = world.fault.timeout_for(call_index)

        if timeout == "lost":
            event.outcome = "TIMEOUT (message not accepted)"
            raise BrokerTimeout("no response from broker")

        self._state.published.append(
            PublishedEvent(
                sequence=len(self._state.published) + 1,
                event_id=event_id,
                payload=payload,
                store_at_publish=dict(self._store_state.data),
            )
        )

        if timeout == "applied":
            event.outcome = "TIMEOUT (but the message WAS accepted)"
            raise BrokerTimeout("no response from broker")

        event.outcome = "ok"
