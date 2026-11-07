from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass
class Event:
    at: datetime
    level: str
    message: str


def parse_line(line: str) -> "Event":
    """Parse one log line."""
    # Split into exactly 3 parts: timestamp, level, and the rest (message)
    ts_str, level, message = line.split(' ', 2)
    message = message.rstrip('\r\n')
    
    # Python 3.9's datetime.fromisoformat doesn't parse the 'Z' suffix natively,
    # and requires exactly 6 digits for fractional seconds if a dot is present.
    clean_ts = ts_str[:-1]
    if '.' in clean_ts:
        main, frac = clean_ts.split('.')
        clean_ts = f"{main}.{frac.ljust(6, '0')}"
        
    at = datetime.fromisoformat(clean_ts).replace(tzinfo=timezone.utc)
    
    return Event(at=at, level=level, message=message)


def gaps(events: list) -> list:
    """Seconds between each pair of consecutive events, as floats."""
    return [
        (events[i].at - events[i - 1].at).total_seconds()
        for i in range(1, len(events))
    ]


def latencies(requests: list, responses: list) -> list:
    """Seconds from requests[i] to responses[i], as floats."""
    if len(requests) != len(responses):
        raise ValueError("requests and responses lists must have the same length")
    
    return [
        (res.at - req.at).total_seconds()
        for req, res in zip(requests, responses)
    ]
