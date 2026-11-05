"""Known-correct, and more elaborate than it needs to be.

Keeps an outbox-style record of the pending notification and clears it only
after the broker has accepted the message, so the marker can only ever cause
an extra publish, never a missing one. Included because this is the shape an
engineer who has been bitten before tends to reach for, and the grader must
accept it too.
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
    outbox_key = f"outbox:{order_id}"
    payload = f"order_shipped:{order_id}"

    event_id = store.get(outbox_key)
    if event_id is None:
        if store.get(f"{outbox_key}:done") == "yes":
            # Already published under a previous event id, and the status was
            # durable before that happened. Nothing left to do.
            return
        candidate = new_id()
        if store.compare_and_set(outbox_key, None, candidate):
            event_id = candidate
        else:
            event_id = store.get(outbox_key)
    assert event_id is not None

    store.put(status_key, "shipped")

    published = False
    for _ in range(8):
        try:
            bus.publish(event_id=event_id, payload=payload)
            published = True
            break
        except BrokerTimeout:
            continue
    if not published:
        raise RuntimeError("broker unreachable")

    store.put(f"{outbox_key}:done", "yes")
    store.delete(outbox_key)
