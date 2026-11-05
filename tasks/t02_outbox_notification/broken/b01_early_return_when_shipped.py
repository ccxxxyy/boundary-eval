"""BROKEN. Expected violation: "no notification was delivered".

The textbook idempotency guard, and the single most common way to lose an
outbox event: "already shipped" is treated as "already notified". Those two
facts become durable at different moments, and the gap between them is where
the notification disappears.

Nothing about this code looks careless. It is defensive, it is idempotent in
the sense most people mean, and it passes every self-check.
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
    if store.get(status_key) == "shipped":
        return

    store.put(status_key, "shipped")
    for _ in range(8):
        try:
            bus.publish(event_id=f"shipped:{order_id}", payload=f"order_shipped:{order_id}")
            return
        except BrokerTimeout:
            continue
    raise RuntimeError("broker unreachable")
