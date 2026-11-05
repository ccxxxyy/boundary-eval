"""BROKEN. Expected violation: "the handler raised BrokerTimeout".

Everything about the ordering and the event id is right. The documented
timeout is simply never handled, so the worker reports a failure for an order
that shipped and was notified.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, EventBus


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    store.put(f"order:{order_id}:status", "shipped")
    bus.publish(event_id=f"shipped:{order_id}", payload=f"order_shipped:{order_id}")
