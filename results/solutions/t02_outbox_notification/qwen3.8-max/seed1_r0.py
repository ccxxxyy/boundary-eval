from typing import Callable

from faultline.api import BrokerTimeout, DurableStore, EventBus


def _get_or_create_event_id(
    store: DurableStore,
    event_key: str,
    new_id: Callable[[], str],
) -> str:
    """Return a durable, order-scoped event id, creating it if needed."""
    while True:
        event_id = store.get(event_key)
        if event_id is not None:
            return event_id

        candidate = new_id()
        if store.compare_and_set(event_key, None, candidate):
            return candidate


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    status_key = f"order:{order_id}:status"
    event_key = f"order:{order_id}:ship_event_id"
    payload = f"order_shipped:{order_id}"

    # The notification must never happen before this durable fact exists.
    store.put(status_key, "shipped")

    # Make the event id durable before any publish attempt.  If we crash and
    # retry, we must reuse the same event id so downstream sees one logical
    # notification, even if duplicates are delivered.
    event_id = _get_or_create_event_id(store, event_key, new_id)

    # Publish until the broker confirms acceptance.  A BrokerTimeout means the
    # outcome is unknown, so retrying with the same event id is safe: if the
    # earlier attempt was accepted, this is a duplicate; if not, this is needed.
    while True:
        try:
            bus.publish(event_id, payload)
            return
        except BrokerTimeout:
            continue
