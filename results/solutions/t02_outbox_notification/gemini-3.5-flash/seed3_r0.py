from __future__ import annotations

from typing import Callable


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    status_key = f"order:{order_id}:status"
    event_id_key = f"order:{order_id}:event_id"
    published_key = f"order:{order_id}:published"

    # 1. Status must be set to 'shipped' before any message is published
    store.put(status_key, "shipped")

    # If already successfully published in a previous run, we are done
    if store.get(published_key) == "true":
        return

    # 2. Get or durably generate a single event_id for this order
    event_id = store.get(event_id_key)
    if event_id is None:
        candidate_id = new_id()
        if store.compare_and_set(event_id_key, None, candidate_id):
            event_id = candidate_id
        else:
            event_id = store.get(event_id_key)
            if event_id is None:
                event_id = candidate_id

    # 3. Publish downstream notification, retrying on BrokerTimeout
    payload = f"order_shipped:{order_id}"
    while True:
        try:
            bus.publish(event_id, payload)
            break
        except Exception:
            pass

    # 4. Record successful publish
    store.put(published_key, "true")
