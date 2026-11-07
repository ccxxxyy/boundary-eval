"""Crash-safe, idempotent processing for an account ledger."""

from faultline.api import DurableStore


_BALANCE_KEY = "ledger:balance"
_MESSAGE_PREFIX = "ledger:message:"
_DONE = "D"


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from durable state alone."""
    encoded = store.get(_BALANCE_KEY)
    return 0 if encoded is None else int(encoded)


def handle_message(
    message_id: str, amount_cents: int, store: DurableStore
) -> None:
    """Apply this message's amount to the balance exactly once.

    A numeric per-message value is a pending record containing the balance
    from immediately before that message. A pending message is always resumed
    before any later message can run, so its balance is either that recorded
    value (the balance write did not happen) or the recorded value plus this
    message's amount (the balance write did happen).
    """
    message_key = _MESSAGE_PREFIX + message_id
    state = store.get(message_key)

    if state == _DONE:
        return

    if state is None:
        balance_before = read_balance(store)
        store.put(message_key, str(balance_before))
    else:
        balance_before = int(state)

    balance_after = balance_before + amount_cents

    # Zero-value messages need no balance write. For other messages, equality
    # with balance_before means the interrupted balance write did not happen.
    # Otherwise, under the single-pending-message invariant, it already did.
    if balance_after != balance_before:
        if read_balance(store) == balance_before:
            store.put(_BALANCE_KEY, str(balance_after))

    # If the process dies before this write, redelivery resolves the pending
    # record without applying the amount again.
    store.put(message_key, _DONE)
