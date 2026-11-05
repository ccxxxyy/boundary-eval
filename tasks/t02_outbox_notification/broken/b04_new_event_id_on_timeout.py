"""BROKEN. Expected violation: "different event ids".

Stores the event id, so redeliveries are fine. Treats a broker timeout as "the
message did not land" and republishes under a new id, which is the one case
where the message probably did land.
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
    status_key = f"order:{order_id}:status"
    event_key = f"order:{order_id}:event-id"

    event_id = store.get(event_key)
    if event_id is None:
        event_id = new_id()
        store.put(event_key, event_id)

    store.put(status_key, "shipped")

    for _ in range(8):
        try:
            bus.publish(event_id=event_id, payload=f"order_shipped:{order_id}")
            return
        except BrokerTimeout:
            event_id = new_id()
            store.put(event_key, event_id)
    raise RuntimeError("broker unreachable")
