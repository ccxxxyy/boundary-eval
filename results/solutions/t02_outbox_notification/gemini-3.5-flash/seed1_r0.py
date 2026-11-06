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
    while True:
        event_id = store.get(event_id_key)
        if event_id is not None:
            break
        candidate_id = new_id()
        if store.compare_and_set(event_id_key, None, candidate_id):
            event_id = candidate_id
            break

    status_key = f"order:{order_id}:status"
    store.put(status_key, "shipped")

    published_key = f"order:{order_id}:published"
    payload = f"order_shipped:{order_id}"

    while store.get(published_key) != "true":
        try:
            bus.publish(event_id, payload)
            store.put(published_key, "true")
            break
        except Exception:
            pass
