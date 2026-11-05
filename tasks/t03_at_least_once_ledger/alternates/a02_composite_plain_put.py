"""Known-correct. Same idea as the reference - one key holding both the
balance and the applied set - but with a plain `put` instead of
compare-and-set, which is sufficient because deliveries never overlap. Here to
stop the grader from quietly requiring compare-and-set."""

from __future__ import annotations

from faultline.api import DurableStore

STATE_KEY = "ledger"


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    raw = store.get(STATE_KEY)
    balance, applied = _parse(raw)
    if message_id in applied:
        return
    store.put(STATE_KEY, f"{balance + amount_cents}|{'.'.join([*applied, message_id])}")


def read_balance(store: DurableStore) -> int:
    balance, _ = _parse(store.get(STATE_KEY))
    return balance


def _parse(raw: str | None) -> tuple[int, list[str]]:
    if not raw:
        return 0, []
    balance, _, applied = raw.partition("|")
    return int(balance), [m for m in applied.split(".") if m]
