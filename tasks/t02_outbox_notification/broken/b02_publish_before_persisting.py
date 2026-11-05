"""BROKEN. Expected violation: "was published while".

Notifies first and records the state afterwards. Reads naturally - tell
everyone, then write it down - and lets a consumer fetch the order and find it
unshipped. If the process dies in between, the notification is permanent and
the order never ships at all.
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
    for _ in range(8):
        try:
            bus.publish(event_id=f"shipped:{order_id}", payload=f"order_shipped:{order_id}")
            break
        except BrokerTimeout:
            continue
    else:
        raise RuntimeError("broker unreachable")

    store.put(f"order:{order_id}:status", "shipped")
