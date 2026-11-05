"""A durable key-value store.

Single-key operations only, and deliberately so: the absence of multi-key
transactions is what forces a solution to think about the order in which it
makes things durable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..world import World


@dataclass
class StoreState:
    data: dict[str, str] = field(default_factory=dict)

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

    def get(self, key: str) -> str | None:
        event = self._world.begin_op("store.get", f"key={key!r}", mutating=False)
        value = self._state.data.get(key)
        event.outcome = f"ok ({value!r})"
        return value

    def put(self, key: str, value: str) -> None:
        self._world.begin_op("store.put", f"key={key!r} value={value!r}", mutating=True)
        self._state.data[key] = value

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool:
        """Set `key` to `new` only if its current value equals `expected`
        (`None` meaning the key must be absent). Returns whether it was set."""
        event = self._world.begin_op(
            "store.compare_and_set",
            f"key={key!r} expected={expected!r} new={new!r}",
            mutating=True,
        )
        if self._state.data.get(key) != expected:
            event.outcome = "ok (False)"
            return False
        self._state.data[key] = new
        event.outcome = "ok (True)"
        return True

    def delete(self, key: str) -> None:
        self._world.begin_op("store.delete", f"key={key!r}", mutating=True)
        self._state.data.pop(key, None)
