from typing import Any, Callable, Optional


class BrokerTimeout(Exception):
    """The broker did not answer."""


def mark_shipped(
    order_id: str,
    store: Any,
    bus: Any,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream.

    This function ensures that:
    1. A stable event_id is persisted for the order to ensure idempotent notifications.
    2. The order status is confirmed as 'shipped' in the store before any notification.
    3. At least one notification is delivered to the event bus.
    4. All notifications for this order use the same event_id.
    5. The function returns normally even if the broker times out during attempts.
    """
    eid_key = f"order:{order_id}:event_id"
    status_key = f"order:{order_id}:status"

    # 1. Ensure we have a stable event_id persisted for this order.
    # We loop until we successfully retrieve an ID from the store.
    # If the store is empty, we generate a candidate and try to set it.
    while True:
        eid = store.get(eid_key)
        if eid is not None:
            break
        candidate_eid = new_id()
        # compare_and_set ensures that if multiple processes were to run,
        # only one ID would ever be written.
        store.compare_and_set(eid_key, None, candidate_eid)

    # 2. Ensure the order is marked as shipped in the durable store.
    # We must confirm the status is 'shipped' before attempting to publish.
    # This ensures that any consumer reading the store after receiving the
    # notification will see the correct status.
    while store.get(status_key) != "shipped":
        store.put(status_key, "shipped")

    # 3. Notify downstream services via the event bus.
    # We retry until the broker acknowledges the message.
    payload = f"order_shipped:{order_id}"
    while True:
        try:
            bus.publish(eid, payload)
            return
        except Exception as e:
            # We catch BrokerTimeout by name to handle cases where the exception
            # class might be defined in a different module than our local one.
            # Since "nothing else is simulated", any exception from publish
            # is treated as a transient broker failure.
            if type(e).__name__ == "BrokerTimeout":
                continue
            raise
