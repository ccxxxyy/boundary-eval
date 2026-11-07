# Task: latency figures from service logs

Write a module that turns log lines from our edge proxies into latency figures.

```python
def parse_line(line: str) -> "Event":
    """Parse one log line."""


def gaps(events: list) -> list:
    """Seconds between each pair of consecutive events, as floats."""


def latencies(requests: list, responses: list) -> list:
    """Seconds from requests[i] to responses[i], as floats."""
```

Log lines look like this:

```
2024-03-05T10:00:00Z INFO accepted connection from 10.0.0.7
2024-03-05T10:00:00.5Z WARN slow upstream
2024-03-05T10:00:01.123456Z INFO done
```

- The timestamp is always UTC, written with a trailing `Z`. Seconds may carry a
  fractional part of 1 to 6 digits, or none.
- Then one space, the level (one word), one space, and the rest of the line is
  the message (it may contain spaces).

`Event` has attributes `at` (a timezone-aware `datetime` in UTC), `level` and
`message`.

`gaps` takes events in order and returns `len(events) - 1` values (an empty
list for fewer than two events).

`latencies` pairs the i-th request with the i-th response. The two lists come
from separate sources; if their lengths differ the data is corrupt and the
function must raise `ValueError` rather than return a partial answer.
