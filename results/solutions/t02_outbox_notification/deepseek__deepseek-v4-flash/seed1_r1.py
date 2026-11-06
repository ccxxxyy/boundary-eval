def mark_shipped(...):
    status_key = ...
    event_key = ...
    status = store.get(status_key)
    if status == "shipped":
        event_id = store.get(event_key)
        if event_id is None:
            event_id = new_id()
            store.put(event_key, event_id)
        _publish_with_retry(bus, event_id, f"order_shipped:{order_id}")
        return
    if store.compare_and_set(status_key, None, "shipped"):
        event_id = new_id()
        store.put(event_key, event_id)
        _publish_with_retry(bus, event_id, f"order_shipped:{order_id}")
        return
    event_id = store.get(event_key)
    if event_id is None:
        event_id = new_id()
        store.put(event_key, event_id)
    _publish_with_retry(bus, event_id, f"order_shipped:{order_id}")
