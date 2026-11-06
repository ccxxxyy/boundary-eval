from typing import Callable, Optional, Protocol


class DurableStore(Protocol):
    """A durable key-value store."""

    def get(self, key: str) -> Optional[str]: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: Optional[str], new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class EventBus(Protocol):
    """A message broker, reached over the network."""

    def publish(self, event_id: str, payload: str) -> None: ...


class BrokerTimeout(Exception):
    """The broker did not answer."""


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream.

    This function is designed to be idempotent and resilient to process crashes
    and network timeouts. It ensures that:
    1. The order status is updated to 'shipped' in the durable store.
    2. At least one notification is sent to the event bus.
    3. All notifications for this order carry the same event_id.
    4. No notification is sent before the store reflects the 'shipped' status.
    """
    eid_key = f"order:{order_id}:event_id"
    status_key = f"order:{order_id}:status"

    # 1. Ensure we have a stable event_id persisted for this order.
    # Since new_id() is not reproducible after a crash, we must store the
    # generated ID to ensure all retries (even across crashes) use the same one.
    eid = store.get(eid_key)
    if eid is None:
        candidate_eid = new_id()
        # Use compare_and_set to handle the case where a previous process
        # crashed after setting the key but before we could read it.
        store.compare_and_set(eid_key, None, candidate_eid)
        # Read back the value that was successfully persisted.
        eid = store.get(eid_key)

    # 2. Ensure the order is marked as shipped in the durable store.
    # This MUST happen before we attempt to publish the event to satisfy the
    # requirement that consumers reading the store find the order shipped.
    if store.get(status_key) != "shipped":
        store.put(status_key, "shipped")

    # 3. Notify downstream services via the event bus.
    # We loop until the broker acknowledges the message. If a BrokerTimeout
    # occurs, we retry with the same event_id. The broker/consumer logic
    # handles deduplication based on this ID.
    payload = f"order_shipped:{order_id}"
    while True:
        try:
            # At this point, eid is guaranteed to be a string and status is 'shipped'.
            bus.publish(eid, payload)
            return
        except BrokerTimeout:
            # The outcome of the publish is unknown. Retry to ensure delivery.
            continue
