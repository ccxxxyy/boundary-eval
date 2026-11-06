"""A durable key-value store.

Single-key operations only, and deliberately so: the absence of multi-key
transactions is what forces a solution to think about the order in which it
makes things durable.

A task may also cap the size of a single value. Without a cap, every task
whose whole state fits in one key has the same universal answer - read the
key, compute, write it back in one atomic put - and the task stops measuring
anything. The cap is not a trick: durable state that grows with the number of
messages processed is a real production bug, and any task that sets a cap says
so in its prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import StoreValueTooLarge
from ..world import World


@dataclass
class StoreState:
    data: dict[str, str] = field(default_factory=dict)
    max_value_bytes: int | None = None

    def describe(self) -> str:
        if not self.data:
            return "store: empty"
        pairs = ", ".join(f"{k}={v!r}" for k, v in sorted(self.data.items()))
        return f"store: {pairs}"


class DurableStore:
    """Every operation is atomic and, once it returns, durable."""

    def __init__(self, world: World, state: StoreState) -> None:
        self._world = world
        self._state = state

    @property
    def max_value_bytes(self) -> int | None:
        return self._state.max_value_bytes

    def _check_size(self, value: str) -> None:
        limit = self._state.max_value_bytes
        if limit is None:
            return
        size = len(value.encode("utf-8"))
        if size > limit:
            raise StoreValueTooLarge(
                f"value of {size} bytes exceeds the {limit}-byte limit for one key"
            )

    def get(self, key: str) -> str | None:
        event = self._world.begin_op("store.get", f"key={key!r}", mutating=False)
        value = self._state.data.get(key)
        event.outcome = f"ok ({value!r})"
        return value

    def put(self, key: str, value: str) -> None:
        event = self._world.begin_op(
            "store.put", f"key={key!r} value={value!r}", mutating=True
        )
        try:
            self._check_size(value)
        except StoreValueTooLarge as exc:
            event.outcome = f"REJECTED ({exc})"
            raise
        self._state.data[key] = value

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool:
        """Set `key` to `new` only if its current value equals `expected`
        (`None` meaning the key must be absent). Returns whether it was set."""
        event = self._world.begin_op(
            "store.compare_and_set",
            f"key={key!r} expected={expected!r} new={new!r}",
            mutating=True,
        )
        try:
            self._check_size(new)
        except StoreValueTooLarge as exc:
            event.outcome = f"REJECTED ({exc})"
            raise
        if self._state.data.get(key) != expected:
            event.outcome = "ok (False)"
            return False
        self._state.data[key] = new
        event.outcome = "ok (True)"
        return True

    def delete(self, key: str) -> None:
        self._world.begin_op("store.delete", f"key={key!r}", mutating=True)
        self._state.data.pop(key, None)
