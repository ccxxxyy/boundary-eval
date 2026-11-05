"""Fill in `mark_shipped`. See prompt.md for the contract."""

from __future__ import annotations

from typing import Callable

from faultline.api import BrokerTimeout, DurableStore, EventBus


def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
    raise NotImplementedError
