from typing import Callable

from faultline.api import BrokerTimeout, DurableStore, EventBus


def _get_or_create_event_id(
    store: DurableStore,
    key: str,
    new_id: Callable[[], str],
) -> str:
    """Return the durable notification ID, creating it if necessary."""
    while True:
        event_id = store.get(key)
        if event_id is not None:
            return event_id

        candidate = new_id()
        if store.compare_and_set(key, None, candidate):
            return candidate

        # A concurrent writer installed an ID; read it on the next iteration.


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    # This must be durable before any notification can be published.
    store.put(f"order:{order_id}:status", "shipped")

    # Persist the ID before publishing. Redeliveries therefore reuse the same
    # ID even if a crash or timeout occurs after the broker accepts a message.
    event_id = _get_or_create_event_id(
        store,
        f"order:{order_id}:shipped:event_id",
        new_id,
    )
    payload = f"order_shipped:{order_id}"

    # A timeout has an unknown outcome. Retrying is safe because every attempt
    # uses the same event ID; returning without a successful response could
    # acknowledge the order without any notification having been accepted.
    while True:
        try:
            bus.publish(event_id, payload)
        except BrokerTimeout:
            continue
        return
