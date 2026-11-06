from __future__ import annotations

from collections.abc import Callable


class DurableStore:
    """A durable key-value store.

    Each operation is atomic, and once it returns, its effect is durable: it
    survives a process crash. The four methods below are the whole API.
    """

    def get(self, key: str) -> str | None:
        raise NotImplementedError

    def put(self, key: str, value: str) -> None:
        raise NotImplementedError

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool:
        """Set `key` to `new` only if its current value equals `expected`
        (pass `None` to mean "the key must be absent").
        Returns whether the write happened."""
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class BrokerTimeout(Exception):
    """The broker did not answer."""


class EventBus:
    """A message broker, reached over the network."""

    def publish(self, event_id: str, payload: str) -> None:
        """Hand a message to the broker for delivery downstream.

        The broker does **not** deduplicate. Every message it accepts is
        delivered, duplicates included. `event_id` is carried along with the
        message and is what a consumer would deduplicate on.

        Raises BrokerTimeout.
        """
        raise NotImplementedError


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    event_id_key = f"order:{order_id}:event_id"
    status_key = f"order:{order_id}:status"
    published_key = f"order:{order_id}:published"

    event_id = store.get(event_id_key)
    if event_id is None:
        event_id = new_id()
        store.put(event_id_key, event_id)

    if store.get(status_key) != "shipped":
        store.put(status_key, "shipped")

    if store.get(published_key) == "1":
        return

    payload = f"order_shipped:{order_id}"
    while True:
        try:
            bus.publish(event_id, payload)
            break
        except BrokerTimeout:
            continue
        except Exception as exc:
            if type(exc).__name__ == "BrokerTimeout":
                continue
            raise

    store.put(published_key, "1")
