"""BROKEN. Expected violation: "different event ids".

Ordering is right and the notification is never lost. The event id, however, is
minted in memory, so a redelivery publishes the same business fact under a new
identity and the consumer's deduplication has nothing to match on. Downstream
ships the parcel twice.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import BrokerTimeout, DurableStore, EventBus


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    event_id = new_id()
    store.put(f"order:{order_id}:status", "shipped")
    for _ in range(8):
        try:
            bus.publish(event_id=event_id, payload=f"order_shipped:{order_id}")
            return
        except BrokerTimeout:
            continue
    raise RuntimeError("broker unreachable")
