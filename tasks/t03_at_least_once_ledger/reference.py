"""Reference solution: fold the amount in and name the message in one write.

The balance key holds either `"<balance>"` or `"<balance>|<message_id>"`. The
second form means: the balance already includes that message, but the
per-message marker has not been written yet. Because the amount and the name
of the message it came from become durable in the *same* compare-and-set,
there is no state in which the balance moved and nothing records why.

Recovery is the interesting half. A handler that finds a name parked in the
balance key finishes that message off - writes its marker and clears the name -
before doing its own work. It does not need to know that message's amount,
only that the balance already includes it. So a crash anywhere in the
three-write sequence is repaired by whichever delivery arrives next, including
a redelivery of the very message that was interrupted.

Durable state stays bounded: one balance, one in-flight name, and one small
marker per distinct message.
"""

from __future__ import annotations

from faultline.api import DurableStore

BALANCE_KEY = "bal"


def _marker(message_id: str) -> str:
    return f"m:{message_id}"


def _parse(raw: str | None) -> tuple[int, str | None]:
    if raw is None:
        return 0, None
    balance, sep, in_flight = raw.partition("|")
    return int(balance), (in_flight if sep else None)


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    while True:
        raw = store.get(BALANCE_KEY)
        balance, in_flight = _parse(raw)

        if in_flight is not None:
            # The balance already includes `in_flight`. Finish recording it,
            # then drop the name so the key is free for the next message.
            store.put(_marker(in_flight), "done")
            store.compare_and_set(BALANCE_KEY, raw, str(balance))
            continue

        if store.get(_marker(message_id)) == "done":
            return

        claimed = f"{balance + amount_cents}|{message_id}"
        if not store.compare_and_set(BALANCE_KEY, raw, claimed):
            continue

        store.put(_marker(message_id), "done")
        store.compare_and_set(BALANCE_KEY, claimed, str(balance + amount_cents))
        return


def read_balance(store: DurableStore) -> int:
    balance, _ = _parse(store.get(BALANCE_KEY))
    return balance
