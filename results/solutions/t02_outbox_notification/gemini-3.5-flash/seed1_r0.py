from __future__ import annotations
from typing import Callable


class BrokerTimeout(Exception):
    """The broker did not answer."""


class DurableStore:
    """A durable key-value store."""


class EventBus:
    """A message broker, reached over the network."""


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    event_id_key = f"order:{order_id}:event_id"
    status_key = f"order:{order_id}:status"
    published_key = f"order:{order_id}:published"

    # 1. Ensure a unique, durable event_id is assigned for this order.
    event_id = store.get(event_id_key)
    while event_id is None:
        candidate_id = new_id()
        if store.compare_and_set(event_id_key, None, candidate_id):
            event_id = candidate_id
        else:
            event_id = store.get(event_id_key)

    # 2. Mark the order status as shipped in the store before any publish attempt.
    store.put(status_key, "shipped")

    # 3. Check if notification was already successfully published in a previous run.
    if store.get(published_key) == "true":
        return

    # 4. Publish notification to downstream services until confirmed by broker.
    payload = f"order_shipped:{order_id}"
    while True:
        try:
            bus.publish(event_id, payload)
            store.put(published_key, "true")
            break
        except Exception as e:
            if type(e).__name__ == "BrokerTimeout" or isinstance(e, BrokerTimeout):
                continue
            raise
