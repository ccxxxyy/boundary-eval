from typing import Callable, Any

def mark_shipped(
    order_id: str,
    store: Any,
    bus: Any,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    event_key = f"order:{order_id}:event_id"
    status_key = f"order:{order_id}:status"
    
    # 1. Get or create a unique event_id for this order's notification.
    # We persist this in the durable store so that if the process crashes
    # and the queue redelivers the job, we use the exact same event_id.
    # This allows downstream consumers to deduplicate the messages.
    event_id = store.get(event_key)
    if event_id is None:
        event_id = new_id()
        store.put(event_key, event_id)
        
    # 2. Mark the order as shipped.
    # This MUST happen before we publish to the event bus. If we publish first
    # and crash, or if the consumer reads the store immediately upon receiving
    # the message, the status must already be 'shipped'.
    store.put(status_key, "shipped")
    
    # 3. Publish the notification.
    # We loop internally to handle BrokerTimeout. If the broker times out,
    # the message may or may not have been accepted. By retrying with the
    # same event_id, we guarantee at-least-once delivery while relying on
    # the consumer to deduplicate.
    payload = f"order_shipped:{order_id}"
    while True:
        try:
            bus.publish(event_id, payload)
            return
        except Exception as e:
            # We check the exception name dynamically to avoid needing to import
            # BrokerTimeout, while ensuring we don't swallow other exceptions
            # (like process kill signals injected by the test environment).
            if type(e).__name__ == 'BrokerTimeout':
                continue
            raise
