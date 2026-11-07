"""Module for parsing edge proxy logs and calculating event gaps and request latencies."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Union


@dataclass(frozen=True)
class Event:
    """Represents a logged proxy event."""

    at: datetime
    level: str
    message: str


def parse_line(line: str) -> Event:
    """Parse one log line into an Event object.

    Log lines follow the format: `<timestamp> <level> <message>`
    where timestamp is ISO 8601 UTC ending with 'Z'.
    """
    cleaned_line = line.rstrip("\r\n")
    parts = cleaned_line.split(" ", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed log line: {line!r}")

    ts_str, level, message = parts

    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"

    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return Event(at=dt, level=level, message=message)


def _get_datetime(obj: Union[Event, datetime]) -> datetime:
    """Extract a datetime instance from an Event object or return the datetime directly."""
    if hasattr(obj, "at"):
        return getattr(obj, "at")
    if isinstance(obj, datetime):
        return obj
    raise TypeError(f"Expected Event or datetime, got {type(obj).__name__}")


def gaps(events: list) -> list:
    """Seconds between each pair of consecutive events, as floats."""
    if len(events) < 2:
        return []

    return [
        (_get_datetime(events[i + 1]) - _get_datetime(events[i])).total_seconds()
        for i in range(len(events) - 1)
    ]


def latencies(requests: list, responses: list) -> list:
    """Seconds from requests[i] to responses[i], as floats."""
    if len(requests) != len(responses):
        raise ValueError(
            f"Mismatched input lengths: {len(requests)} requests vs {len(responses)} responses"
        )

    return [
        (_get_datetime(resp) - _get_datetime(req)).total_seconds()
        for req, resp in zip(requests, responses)
    ]
