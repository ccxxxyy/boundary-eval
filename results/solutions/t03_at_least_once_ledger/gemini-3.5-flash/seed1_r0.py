import json
from typing import Any


def _get_state(store: Any) -> tuple[int, set[str], str | None]:
    """Retrieve current balance and processed message IDs from store."""
    while True:
        try:
            raw = store.get("state")
            if raw is None:
                return 0, set(), None
            data = json.loads(raw)
            return int(data["balance"]), set(data["processed"]), raw
        except Exception:
            pass


def handle_message(message_id: str, amount_cents: int, store: Any) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""
    while True:
        balance, processed, raw = _get_state(store)
        if message_id in processed:
            return

        new_balance = balance + amount_cents
        processed.add(message_id)
        new_data = {
            "balance": new_balance,
            "processed": sorted(processed),
        }
        new_raw = json.dumps(new_data)

        try:
            success = store.compare_and_set("state", raw, new_raw)
            if success:
                return
        except Exception:
            pass


def read_balance(store: Any) -> int:
    """Return the current balance, in cents, from whatever `handle_message`

    has written. Called in a fresh process, so it must work from durable state
    alone.
    """
    while True:
        try:
            raw = store.get("state")
            if raw is None:
                return 0
            data = json.loads(raw)
            return int(data["balance"])
        except Exception:
            pass
