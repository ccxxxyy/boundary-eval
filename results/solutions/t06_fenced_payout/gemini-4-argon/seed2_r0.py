from __future__ import annotations

from typing import Callable, Protocol


class DurableStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class LegacyTransferAPI(Protocol):
    def transfer(self, amount_cents: int) -> str: ...


COMPLETED = "completed"
NEEDS_REVIEW = "needs_review"
TERMINAL_STATES = (COMPLETED, NEEDS_REVIEW)


def _ is_transfer_timeout(exc: BaseException) -> bool:
    return any(cls.__name__ == "TransferTimeout" for cls in type(exc).__mro__)
```
 Let's make sure there is no typo in `_is_transfer_timeout` (no space after `_`). Let's produce the clean final code block.```python
from __future__ import annotations

from typing import Callable, Protocol


class DurableStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class LegacyTransferAPI(Protocol):
    def transfer(self, amount_cents: int) -> str: ...


COMPLETED = "completed"
NEEDS_REVIEW = "needs_review"
TERMINAL_STATES = (COMPLETED, NEEDS_REVIEW)


def _is_transfer_timeout(exc: BaseException) -> bool:
    return any(cls.__name__ == "TransferTimeout" for cls in type(exc).__mro__)


def _resolve_existing(store: DurableStore, state_key: str) -> str:
    while True:
        current = store.get(state_key)
        if current in TERMINAL_STATES:
            return current
        if store.compare_and_set(state_key, current, NEEDS_REVIEW):
            return NEEDS_REVIEW


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents` at most once.

    Return "completed" if the money has moved exactly once and that fact is
    durably recorded. Return "needs_review" if the outcome is unknown or
    cannot be completed safely, so a person can reconcile it.
    """
    state_key = f"payout:{payout_id}:state"

    current
