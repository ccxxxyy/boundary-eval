from __future__ import annotations

from typing import Callable


class BrokerTimeout(Exception):
    """The broker did not answer."""


class DurableStore:
    """A durable key-value store."""

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class EventBus:
    """A message broker, reached over the network."""

    def publish(self, event_id: str, payload: str) -> None: ...


def _get_or_create_event_id(
    order_id: str,
    store: DurableStore,
    new_id: Callable[[], str],
) -> str:
    """Retrieve existing event_id for the order or create and persist a new one."""
    event_id_key = f"order:{order_id}:event_id"
    eid = store.get(event_id_key)
    if eid is not None:
        return eid

    candidate = new_id()
    if store.compare_and_set(event_id_key, None, candidate):
        return candidate

    existing = store.get(event_id_key)
    if existing is not None:
        return existing
    return candidate


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    status_key = f"order:{order_id}:status"
    published_key = f"order:{order_id}:published"
    payload = f"order_shipped:{order_id}"

    # 1. Obtain consistent event_id for this order shipment
    eid = _get_or_create_event_id(order_id, store, new_id)

    # 2. Mark status as shipped in store before any network call
    store.put(status_key, "shipped")

    # 3. Publish notification downstream if not already recorded as published
    if store.get(published_key) != "true":
        while True:
            try:
                bus.publish(eid, payload)
            except Exception:
                continue
            store.put(published_key, "true")
            break
