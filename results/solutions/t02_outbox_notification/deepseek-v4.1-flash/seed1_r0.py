from typing import Callable

from faultline.api import BrokerTimeout, DurableStore, EventBus


def _status_key(order_id: str) -> str:
    return f"order:{order_id}:status"


def _event_id_key(order_id: str) -> str:
    return f"order:{order_id}:event_id"


def _get_or_create_event_id(
    store: DurableStore,
    key: str,
    new_id: Callable[[], str],
) -> str:
    """Return the already-persisted event id, or durably create one.

    The event id must never change once it has been persisted: a redelivery
    after a crash or a broker timeout must publish with the same id so that
    downstream consumers can deduplicate.
    """
    event_id = store.get(key)

    while event_id is None:
        candidate = new_id()
        if store.compare_and_set(key, None, candidate):
            return candidate

        # Another attempt already persisted an id (or, defensively, the CAS
        # failed for some reason). Re-read and use whatever is durable.
        event_id = store.get(key)

    return event_id


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    status_key = _status_key(order_id)
    event_key = _event_id_key(order_id)

    # The status write is durable before any publish. If we crash before this
    # takes effect, we have not published. If it returns, downstream readers
    # will see the order as shipped before they can receive a notification.
    store.put(status_key, "shipped")

    # Persist a single event id for this order before publishing. Every retry
    # and every redelivery will reuse this exact id.
    event_id = _get_or_create_event_id(store, event_key, new_id)

    payload = f"order_shipped:{order_id}"

    # The broker does not deduplicate. A BrokerTimeout may mean the message was
    # accepted or it may mean it was not. Retrying with the same event_id is
    # safe in both cases: duplicates are collapsed by downstream consumers.
    while True:
        try:
            bus.publish(event_id, payload)
            return
        except BrokerTimeout:
            continue
