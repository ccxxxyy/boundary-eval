import time
from typing import Callable


class DurableStore:
    """A durable key-value store.

    Each operation is atomic, and once it returns, its effect is durable: it
    survives a process crash. The four methods below are the whole API.
    """

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool:
        """Set `key` to `new` only if its current value equals `expected`
        (pass `None` to mean "the key must be absent").
        Returns whether the write happened."""

    def delete(self, key: str) -> None: ...


class EventBus:
    """A message broker, reached over the network."""

    def publish(self, event_id: str, payload: str) -> None:
        """Hand a message to the broker for delivery downstream.

        The broker does **not** deduplicate. Every message it accepts is
        delivered, duplicates included. `event_id` is carried along with the
        message and is what a consumer would deduplicate on.

        Raises BrokerTimeout.
        """


class BrokerTimeout(Exception):
    """The broker did not answer."""


def new_id() -> str:
    """Return a fresh unique identifier, like `uuid4().hex`.

    Every call returns a different value, and the values are *not* reproducible
    after a restart: a new process calling `new_id()` gets different output
    than the one before it did.
    """
    ...


def _publish_with_retry(bus: EventBus, event_id: str, payload: str) -> None:
    """Publish a message, retrying on BrokerTimeout until success."""
    while True:
        try:
            bus.publish(event_id, payload)
            return
        except BrokerTimeout:
            # The broker may have accepted the message or not.
            # We cannot tell, so we retry with the same event_id.
            # A small sleep prevents busy-waiting.
            time.sleep(0.1)


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    status_key = f"order:{order_id}:status"
    event_key = f"order:{order_id}:event_id"

    # Check current state
    status = store.get(status_key)
    if status == "shipped":
        # Order already marked shipped. Reuse or create event_id.
        event_id = store.get(event_key)
        if event_id is None:
            # This can happen if a previous attempt crashed after setting
            # status but before storing the event_id. Generate a new one.
            event_id = new_id()
            store.put(event_key, event_id)
        # Publish (or republish) the notification.
        _publish_with_retry(bus, event_id, f"order_shipped:{order_id}")
        return

    # Order not yet shipped. Atomically set status to shipped.
    # We expect the key to be absent (None).
    if store.compare_and_set(status_key, None, "shipped"):
        # We successfully set the status. Now store the event_id.
        event_id = new_id()
        store.put(event_key, event_id)
        # Publish the notification.
        _publish_with_retry(bus, event_id, f"order_shipped:{order_id}")
        return

    # compare_and_set returned False – the key already exists.
    # This should not happen because calls never overlap, but handle it
    # gracefully by falling through to the shipped case.
    # (The status must now be "shipped" because no other value is ever written.)
    event_id = store.get(event_key)
    if event_id is None:
        event_id = new_id()
        store.put(event_key, event_id)
    _publish_with_retry(bus, event_id, f"order_shipped:{order_id}")
