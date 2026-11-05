"""BROKEN. Expected violation: "no notification was delivered".

Keeps a proper "notified" marker, which is the right idea, and sets it before
the publish it is supposed to be recording. A crash in that window leaves a
shipped order the system believes it has already announced.
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
    notified_key = f"order:{order_id}:notified"

    store.put(status_key, "shipped")
    if store.get(notified_key) == "yes":
        return

    store.put(notified_key, "yes")
    for _ in range(8):
        try:
            bus.publish(event_id=f"shipped:{order_id}", payload=f"order_shipped:{order_id}")
            return
        except BrokerTimeout:
            continue
    raise RuntimeError("broker unreachable")
