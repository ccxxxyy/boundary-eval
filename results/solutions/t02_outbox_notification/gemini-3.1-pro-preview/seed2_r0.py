from typing import Callable

def mark_shipped(
    order_id: str,
    store: "DurableStore",
    bus: "EventBus",
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    event_key = f"order:{order_id}:event_id"
    status_key = f"order:{order_id}:status"
    
    # 1. Durably store a unique event ID for this order.
    # This ensures that if we crash and the queue redelivers, we reuse the same
    # event ID, allowing downstream consumers to deduplicate the notification.
    event_id = store.get(event_key)
    if event_id is None:
        event_id = new_id()
        store.put(event_key, event_id)
        
    # 2. Mark the order as shipped.
    # This must happen BEFORE publishing to the bus. Since `store.put` is atomic
    # and durable, once it returns, any consumer receiving the event and reading
    # from the store is guaranteed to see the "shipped" status.
    store.put(status_key, "shipped")
    
    # 3. Publish the notification.
    # We loop on BrokerTimeout because the outcome is unknown and we must not let
    # the exception escape. If the broker accepted it but the response timed out,
    # the retry will send a duplicate with the SAME event_id, which is safe.
    payload = f"order_shipped:{order_id}"
    while True:
        try:
            bus.publish(event_id, payload)
            break
        except BrokerTimeout:
            continue
