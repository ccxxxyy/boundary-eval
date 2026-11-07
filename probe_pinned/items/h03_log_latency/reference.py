from datetime import datetime, timezone
from typing import List, NamedTuple


class Event(NamedTuple):
    at: datetime
    level: str
    message: str


def parse_line(line: str) -> Event:
    stamp, level, message = line.rstrip("\n").split(" ", 2)
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in stamp else "%Y-%m-%dT%H:%M:%SZ"
    at = datetime.strptime(stamp, fmt).replace(tzinfo=timezone.utc)
    return Event(at, level, message)


def gaps(events: List[Event]) -> List[float]:
    return [(b.at - a.at).total_seconds() for a, b in zip(events, events[1:])]


def latencies(requests: List[Event], responses: List[Event]) -> List[float]:
    if len(requests) != len(responses):
        raise ValueError("request/response count mismatch")
    return [(b.at - a.at).total_seconds() for a, b in zip(requests, responses)]
