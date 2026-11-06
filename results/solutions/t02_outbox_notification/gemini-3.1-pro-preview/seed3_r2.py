from typing import Callable

def mark_shipped(
    order_id: str,
    store: 'DurableStore',
    bus: 'EventBus',
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    event_id_key = f"order:{order_id}:event_id"
    status_key = f"order:{order_id}:status"

    # 1. Ensure we have a durable event_id for this order to allow downstream deduplication.
    # Since calls never overlap, a simple get-then-put is safe from race conditions.
    event_id = store.get(event_id_key)
    if event_id is None:
        event_id = new_id()
        store.put(event_id_key, event_id)

    # 2. Ensure the order is marked as shipped before we attempt to publish.
    # We check first to avoid unnecessary writes if recovering from a crash after this step.
    if store.get(status_key) != "shipped":
        store.put(status_key, "shipped")

    # 3. Publish the notification.
    # We loop to handle BrokerTimeout. If the process crashes here, the queue will redeliver,
    # and we will safely reuse the same event_id and skip the status update.
    payload = f"order_shipped:{order_id}"
    while True:
        try:
            bus.publish(event_id, payload)
            break
        except Exception as e:
            # Catch BrokerTimeout by name since it is not injected into our global namespace
            if type(e).__name__ == "BrokerTimeout":
                continue
            raise
