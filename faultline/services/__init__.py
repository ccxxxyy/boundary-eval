"""Simulated outside systems.

Each service is a facade over a piece of durable state. All of them funnel
their operations through `World.begin_op`, so adding a service automatically
gives the injector new crash points and new timeout points without the
injector knowing anything about it.
"""

from .bus import BusState, EventBus, PublishedEvent
from .gateway import Charge, GatewayState, PaymentGateway
from .inventory import InventoryState, SeatInventory
from .legacy import LegacyState, LegacyTransferAPI, Transfer
from .store import DurableStore, StoreState

__all__ = [
    "BusState",
    "Charge",
    "DurableStore",
    "EventBus",
    "GatewayState",
    "InventoryState",
    "LegacyState",
    "LegacyTransferAPI",
    "PaymentGateway",
    "PublishedEvent",
    "SeatInventory",
    "StoreState",
    "Transfer",
]
