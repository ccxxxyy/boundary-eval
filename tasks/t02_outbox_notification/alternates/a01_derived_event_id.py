"""Known-correct, deliberately minimal.

Derives the event id from the order id instead of storing one, and keeps no
"already notified" bookkeeping at all: it simply republishes on every
redelivery. Duplicates carrying one event id are exactly what the contract
permits, so this is correct, and a grader that insisted on a notified marker
would be producing false failures.
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
    store.put(f"order:{order_id}:status", "shipped")
    for _ in range(8):
        try:
            bus.publish(event_id=f"shipped:{order_id}", payload=f"order_shipped:{order_id}")
            return
        except BrokerTimeout:
            continue
    raise RuntimeError("broker unreachable")
