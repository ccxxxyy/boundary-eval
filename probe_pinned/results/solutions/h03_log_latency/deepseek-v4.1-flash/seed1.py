"""Turn edge-proxy log lines into latency figures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re


_TIMESTAMP_RE = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,6}))?"
    r"Z$"
)


@dataclass(frozen=True)
class Event:
    at: datetime
    level: str
    message: str


def _parse_timestamp(value: str) -> datetime:
    match = _TIMESTAMP_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid timestamp: {value!r}")

    base = datetime.strptime(match.group("base"), "%Y-%m-%dT%H:%M:%S")
    fraction = match.group("fraction")
    microsecond = int(fraction.ljust(6, "0")) if fraction else 0

    return base.replace(microsecond=microsecond, tzinfo=timezone.utc)


def parse_line(line: str) -> Event:
    """Parse one log line."""
    raw = line.rstrip("\r\n")
    parts = raw.split(" ", 2)

    if len(parts) != 3:
        raise ValueError(f"malformed log line: {line!r}")

    timestamp, level, message = parts
    if not level:
        raise ValueError(f"malformed log line: {line!r}")

    return Event(
        at=_parse_timestamp(timestamp),
        level=level,
        message=message,
    )


def gaps(events: list[Event]) -> list[float]:
    """Seconds between each pair of consecutive events, as floats."""
    return [
        (current.at - previous.at).total_seconds()
        for previous, current in zip(events, events[1:])
    ]


def latencies(requests: list[Event], responses: list[Event]) -> list[float]:
    """Seconds from requests[i] to responses[i], as floats."""
    if len(requests) != len(responses):
        raise ValueError("request and response counts differ")

    return [
        (response.at - request.at).total_seconds()
        for request, response in zip(requests, responses)
    ]
