import json

_LEDGER_KEY = "ledger_state"

def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """
    Apply the message's amount to the balance exactly once.
    Uses a single key to store the entire state (balance + set of processed IDs)
    so that the update is atomic and durable.
    """
    # Read current state
    raw = store.get(_LEDGER_KEY)
    if raw is None:
        state = {"balance": 0, "processed": []}
    else:
        state = json.loads(raw)

    # Already processed → nothing to do
    if message_id in state["processed"]:
        return

    # Apply the change
    state["balance"] += amount_cents
    state["processed"].append(message_id)

    # Write back atomically
    store.put(_LEDGER_KEY, json.dumps(state, sort_keys=True))


def read_balance(store: DurableStore) -> int:
    """
    Return the current balance from durable state.
    Works in a fresh process because all state is in the store.
    """
    raw = store.get(_LEDGER_KEY)
    if raw is None:
        return 0
    state = json.loads(raw)
    return state["balance"]
