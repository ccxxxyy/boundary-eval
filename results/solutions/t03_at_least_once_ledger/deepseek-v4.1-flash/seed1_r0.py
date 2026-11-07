from faultline.api import DurableStore

_HEAD_KEY = "ledger:head"
_MSG_PREFIX = "msg:"
_NODE_PREFIX = "ledger:node:"
_CHUNK_SIZE = 24
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ALPHABET_INDEX = {ch: i for i, ch in enumerate(_ALPHABET)}


def _to_base62(n: int) -> str:
    if n < 0:
        raise ValueError("negative integer")
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 62)
        out.append(_ALPHABET[r])
    return "".join(reversed(out))


def _from_base62(s: str) -> int:
    value = 0
    for ch in s:
        value = value * 62 + _ALPHABET_INDEX[ch]
    return value


def _marker_key(message_id: str) -> str:
    return _MSG_PREFIX + message_id


def _node_prev_key(node_id: int) -> str:
    return f"{_NODE_PREFIX}{node_id}:prev"


def _node_count_key(node_id: int) -> str:
    return f"{_NODE_PREFIX}{node_id}:count"


def _node_amount_key(node_id: int, index: int) -> str:
    return f"{_NODE_PREFIX}{node_id}:a:{index}"


def _read_head(store: DurableStore) -> int:
    value = store.get(_HEAD_KEY)
    if value is None:
        return 0
    return _from_base62(value)


def _read_node_prev(store: DurableStore, node_id: int) -> int:
    value = store.get(_node_prev_key(node_id))
    if value is None:
        return 0
    return _from_base62(value)


def _write_node(
    store: DurableStore, node_id: int, prev_node_id: int, amount_cents: int
) -> None:
    text = str(amount_cents)
    chunks = [
        text[i : i + _CHUNK_SIZE]
        for i in range(0, len(text), _CHUNK_SIZE)
    ]
    if not chunks:
        chunks = ["0"]

    for index, chunk in enumerate(chunks):
        store.put(_node_amount_key(node_id, index), chunk)

    store.put(_node_count_key(node_id), _to_base62(len(chunks)))
    store.put(_node_prev_key(node_id), _to_base62(prev_node_id))


def _chain_contains(store: DurableStore, head: int, target: int) -> bool:
    node = head
    while node > 0:
        if node == target:
            return True
        if node < target:
            return False
        node = _read_node_prev(store, node)
    return False


def _finish_prepared(
    store: DurableStore, marker_key: str, node_id: int, amount_cents: int
) -> None:
    while True:
        head = _read_head(store)

        if head == node_id:
            store.put(marker_key, "A")
            return

        if head > node_id:
            if _chain_contains(store, head, node_id):
                store.put(marker_key, "A")
                return

            new_node_id = head + 1
            store.put(marker_key, "P:" + _to_base62(new_node_id))
            node_id = new_node_id
            continue

        _write_node(store, node_id, head, amount_cents)

        expected = None if head == 0 else _to_base62(head)
        new = _to_base62(node_id)

        if store.compare_and_set(_HEAD_KEY, expected, new):
            store.put(marker_key, "A")
            return


def handle_message(
    message_id: str, amount_cents: int, store: DurableStore
) -> None:
    marker_key = _marker_key(message_id)
    marker = store.get(marker_key)

    if marker == "A":
        return

    if marker is not None and marker.startswith("P:"):
        node_id = _from_base62(marker[2:])
        _finish_prepared(store, marker_key, node_id, amount_cents)
        return

    head = _read_head(store)
    node_id = head + 1
    store.put(marker_key, "P:" + _to_base62(node_id))
    _finish_prepared(store, marker_key, node_id, amount_cents)


def read_balance(store: DurableStore) -> int:
    head = _read_head(store)
    total = 0
    node = head
    seen = set()

    while node > 0 and node not in seen:
        seen.add(node)

        prev = _read_node_prev(store, node)

        count_value = store.get(_node_count_key(node))
        count = 1 if count_value is None else _from_base62(count_value)

        parts = []
        for index in range(count):
            part = store.get(_node_amount_key(node, index))
            if part is not None:
                parts.append(part)

        text = "".join(parts)
        if text:
            total += int(text)

        node = prev

    return total
