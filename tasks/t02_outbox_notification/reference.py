"""Reference solution.

Three decisions carry the whole thing:

  * the event id is durable before it is used, so every redelivery publishes
    under the same id and the consumer's deduplication works;
  * the status is durable *before* the first publish, so no consumer can read
    the order back and find it unshipped;
  * being already shipped is not treated as being already notified, so a
    redelivery still publishes. Duplicates are the acceptable outcome here -
    they carry the same event id. A missing notification is not.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import BrokerTimeout, DurableStore, EventBus

MAX_PUBLISH_ATTEMPTS = 8


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
        candidate = new_id()
        if store.compare_and_set(event_key, None, candidate):
            event_id = candidate
        else:
            event_id = store.get(event_key)
    assert event_id is not None

    store.put(status_key, "shipped")

    for _ in range(MAX_PUBLISH_ATTEMPTS):
        try:
            bus.publish(event_id=event_id, payload=f"order_shipped:{order_id}")
            return
        except BrokerTimeout:
            # The message may already be on its way. Republishing under the
            # same event id is safe; giving up is not.
            continue

    raise RuntimeError(f"broker unreachable for order {order_id}")
