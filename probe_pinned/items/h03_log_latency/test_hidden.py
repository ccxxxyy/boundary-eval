from datetime import datetime, timedelta, timezone

import pytest

from probe_support import solution

mod = solution()

LINES = [
    "2024-03-05T10:00:00Z INFO accepted connection from 10.0.0.7",
    "2024-03-05T10:00:00.5Z WARN slow upstream",
    "2024-03-05T10:00:01.123456Z INFO done",
    "2024-03-05T10:00:02.25Z ERROR reset by peer",
]


def test_parse_line_fields():
    event = mod.parse_line(LINES[0])
    assert event.at == datetime(2024, 3, 5, 10, 0, 0, tzinfo=timezone.utc)
    assert event.at.utcoffset() == timedelta(0)
    assert event.level == "INFO"
    assert event.message == "accepted connection from 10.0.0.7"


def test_fractional_seconds_of_any_width():
    ats = [mod.parse_line(line).at for line in LINES]
    assert [a.microsecond for a in ats] == [0, 500000, 123456, 250000]


def test_gaps():
    events = [mod.parse_line(line) for line in LINES]
    assert mod.gaps(events) == pytest.approx([0.5, 0.623456, 1.126544])
    assert mod.gaps(events[:1]) == []


def test_latencies_and_length_mismatch():
    events = [mod.parse_line(line) for line in LINES]
    assert mod.latencies(events[:2], events[2:]) == pytest.approx([1.123456, 1.75])
    with pytest.raises(ValueError):
        mod.latencies(events[:3], events[3:])
