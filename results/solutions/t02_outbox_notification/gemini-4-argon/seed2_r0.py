from __future__ import annotations

from typing import Callable, Protocol


class DurableStore(Protocol):
    """A durable key-value store."""

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class EventBus(Protocol):
    """A message broker, reached over the network."""

    def publish(self, event_id: str, payload: str) -> None: ...


class BrokerTimeout(Exception):
    """The broker did not answer."""


def _is_broker_timeout(exc: BaseException) -> bool:
    return any(cls.__name__ == "BrokerTimeout" for cls in type(exc).__mro__)


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    status_key = f"order:{order_id}:status"
    event_key = f"order:{order_id}:event_id"
    sent_key = f"order:{order_id}:sent"

    if store.get(sent_key) == "1":
        if store.get(status_key) != "shipped":
            store.put(status_key, "shipped")
        return

    event_id = store.get(event_key)
    if event_id is None:
        event_id = new_id()
        store.put(event_key, event_id)

    if store.get(status_key) != "shipped":
        store.put(status_key, "shipped")

    payload = f"order_shipped:{order_id}"
    while True:
        try:
            bus.publish(event_id, payload)
            break
        except Exception as exc:
            if not _is_broker_timeout(exc):
                raise

    store.put(sent_key, "1")
