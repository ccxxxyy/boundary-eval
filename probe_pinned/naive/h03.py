from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise


@dataclass
class Event:
    at: datetime
    level: str
    message: str


def parse_line(line):
    stamp, level, message = line.split(" ", 2)
    return Event(datetime.fromisoformat(stamp), level, message)


def gaps(events):
    return [(b.at - a.at).total_seconds() for a, b in pairwise(events)]


def latencies(requests, responses):
    return [(b.at - a.at).total_seconds() for a, b in zip(requests, responses, strict=True)]
