"""Exactly-once payment handling for an order pipeline."""

import json
from typing import Callable

from faultline.api import DurableStore, GatewayTimeout, PaymentGateway


def _store_key(order_id: str) -> str:
    return f"payment_order:{order_id}"


def _load_state(raw: str) -> dict:
    return json.loads(raw)


def _save_state(store: DurableStore, key: str, state: dict) -> None:
    store.put(key, json.dumps(state))


def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id.

    The idempotency key is persisted before the first charge attempt, so a
    retry or a process restart always reuses the same key.  The gateway then
    guarantees at most one charge for that key.
    """
    key = _store_key(order_id)
    raw = store.get(key)

    if raw is None:
        state = {
            "idempotency_key": new_id(),
            "charge_id": None,
            "amount_cents": amount_cents,
        }
        encoded = json.dumps(state)
        if not store.compare_and_set(key, None, encoded):
            # Another writer got there first (not expected without overlap,
            # but handle it defensively).
            raw = store.get(key)
            if raw is None:
                # The store said the key existed, but we cannot read it.
                # Write our state so we can make progress.
                store.put(key, encoded)
            else:
                state = _load_state(raw)
    else:
        state = _load_state(raw)

    if state.get("charge_id") is not None:
        return state["charge_id"]

    idem = state["idempotency_key"]

    while True:
        # Resolve any charge that a previous attempt may have created before
        # the process died or a timeout hid the result.
        existing = gateway.lookup(idem)
        if existing is not None:
            state["charge_id"] = existing
            _save_state(store, key, state)
            return existing

        try:
            charge_id = gateway.charge(idem, amount_cents)
        except GatewayTimeout:
            # Outcome unknown: loop, look it up, and retry with the same key.
            continue

        state["charge_id"] = charge_id
        _save_state(store, key, state)
        return charge_id
