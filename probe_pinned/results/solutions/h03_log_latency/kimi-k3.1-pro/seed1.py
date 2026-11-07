"""Parse edge-proxy logs and calculate event timing figures."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re


@dataclass(frozen=True)
class Event:
    """A single parsed log event."""

    at: datetime
    level: str
    message: str


_LINE_RE = re.compile(
    r"(?P<base>[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,6}))?Z "
    r"(?P<level>\S+) (?P<message>.*)"
)


def parse_line(line: str) -> "Event":
    """Parse one log line, raising ValueError if it is malformed."""
    # Accept lines obtained directly from file iteration without including
    # their line ending in the message.
    if line.endswith("\r\n"):
        line = line[:-2]
    elif line.endswith(("\r", "\n")):
        line = line[:-1]

    match = _LINE_RE.fullmatch(line)
    if match is None:
        raise ValueError("malformed log line")

    try:
        at = datetime.strptime(match.group("base"), "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValueError("invalid timestamp in log line") from exc

    fraction = match.group("fraction")
    microsecond = int(fraction.ljust(6, "0")) if fraction is not None else 0
    at = at.replace(microsecond=microsecond, tzinfo=timezone.utc)

    return Event(
        at=at,
        level=match.group("level"),
        message=match.group("message"),
    )


def gaps(events: list) -> list:
    """Return seconds between each pair of consecutive events."""
    return [
        (current.at - previous.at).total_seconds()
        for previous, current in zip(events, events[1:])
    ]


def latencies(requests: list, responses: list) -> list:
    """Return seconds from each request to its corresponding response."""
    if len(requests) != len(responses):
        raise ValueError("requests and responses must have the same length")

    return [
        (response.at - request.at).total_seconds()
        for request, response in zip(requests, responses)
    ]
