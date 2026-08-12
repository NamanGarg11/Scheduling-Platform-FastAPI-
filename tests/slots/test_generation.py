"""Pure slot-generation engine tests (Phase S1).

The first test in this file is the normative stepping specification (ADR-003): it is
preserved verbatim from the pre-S1 suite, only its fixture construction changed from ORM
models to the pure dataclasses. Do not "improve" it into a 5-slot interpretation.
"""

from datetime import date, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.availability.enums import DayOfWeek
from app.slots.slot_generation import (
    AvailabilityRule,
    EventTypeSpec,
    ExceptionKind,
    ExceptionRule,
    SlotCandidate,
    SlotGenerationEngine,
    TimeWindow,
    apply_exceptions,
    exclude_overlapping_booked,
    merge_windows,
    occupied,
    overlaps_booked,
    parse_time_on_date,
    split_into_slots,
    subtract_windows,
    windows_for_weekday_rule,
)

UTC = timezone.utc
LONDON = ZoneInfo("Europe/London")
KOLKATA = ZoneInfo("Asia/Kolkata")

MONDAY = date(2026, 8, 10)  # 2026-08-10 is a Monday
SUNDAY_SPRING = date(2026, 3, 29)  # Europe/London spring forward: 01:00 GMT -> 02:00 BST
SUNDAY_AUTUMN = date(2026, 10, 25)  # Europe/London autumn back: 02:00 BST -> 01:00 GMT


def _spec(
    duration_minutes: int = 30,
    buffer_before_minutes: int = 0,
    buffer_after_minutes: int = 0,
) -> EventTypeSpec:
    return EventTypeSpec(
        duration_minutes=duration_minutes,
        buffer_before_minutes=buffer_before_minutes,
        buffer_after_minutes=buffer_after_minutes,
    )


def _rule(
    day_of_week: DayOfWeek,
    start_time: time = time(9, 0),
    end_time: time = time(17, 0),
    is_available: bool = True,
) -> AvailabilityRule:
    return AvailabilityRule(
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        is_available=is_available,
    )


def _window(h: int, m: int, end_h: int, end_m: int, tz=KOLKATA) -> TimeWindow:
    return TimeWindow(
        start=parse_time_on_date(MONDAY, time(h, m), tz),
        end=parse_time_on_date(MONDAY, time(end_h, end_m), tz),
    )


# ---------------------------------------------------------------------------
# Stepping semantics (ADR-003) — the pinned specification, preserved verbatim.
# ---------------------------------------------------------------------------


def test_generates_slots_with_buffers():
    event_type = _spec(
        duration_minutes=30,
        buffer_before_minutes=5,
        buffer_after_minutes=10,
    )

    availability = [
        _rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0)),
    ]

    engine = SlotGenerationEngine()

    slots = engine.generate(
        event_type=event_type,
        availability=availability,
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )

    assert len(slots) == 4

    assert slots[0].start_at.hour == 9
    assert slots[0].start_at.minute == 5
    assert slots[0].end_at.hour == 9
    assert slots[0].end_at.minute == 35

    assert [(s.start_at.hour, s.start_at.minute) for s in slots] == [
        (9, 5),
        (9, 50),
        (10, 35),
        (11, 20),
    ]
    # Last candidate's occupied interval ends exactly at the window end (touching).
    assert occupied(slots[-1], event_type).end == parse_time_on_date(
        MONDAY, time(12, 0), KOLKATA
    )


def test_generates_slots_without_buffers():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert [(s.start_at.hour, s.start_at.minute) for s in slots] == [
        (9, 0),
        (9, 30),
        (10, 0),
        (10, 30),
        (11, 0),
        (11, 30),
    ]


def test_generates_slots_with_buffer_before_only():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30, buffer_before_minutes=5),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert [(s.start_at.hour, s.start_at.minute) for s in slots] == [
        (9, 5),
        (9, 40),
        (10, 15),
        (10, 50),
        (11, 25),
    ]


def test_generates_slots_with_buffer_after_only():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30, buffer_after_minutes=10),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    # occupied = 40min; the last candidate's occupied interval ends at 11:40,
    # leaving only 20min to the window end — not enough for another meeting.
    assert [(s.start_at.hour, s.start_at.minute) for s in slots] == [
        (9, 0),
        (9, 40),
        (10, 20),
        (11, 0),
    ]


def test_generates_slots_one_minute_duration():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=1),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(17, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert len(slots) == 480  # 480 minutes of availability, 1-minute meetings


def test_generates_slots_120_minute_window():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=60),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(11, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert [(s.start_at.hour, s.start_at.minute) for s in slots] == [(9, 0), (10, 0)]


# ---------------------------------------------------------------------------
# Weekday expansion
# ---------------------------------------------------------------------------


def test_multi_day_range_skips_weekends():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0))],
        start_date=MONDAY,  # Monday
        end_date=date(2026, 8, 16),  # Sunday
        timezone="Asia/Kolkata",
    )
    assert slots
    assert all(s.start_at.date() == MONDAY for s in slots)
    assert len(slots) == 6


def test_unavailable_rule_produces_no_slots():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0), is_available=False)],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert slots == []


def test_multiple_rules_same_day_are_merged():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[
            _rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0)),
            _rule(DayOfWeek.MONDAY, time(11, 0), time(15, 0)),
        ],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    # Merged to a single 09:00-15:00 window.
    assert len(slots) == 12


# ---------------------------------------------------------------------------
# merge_windows
# ---------------------------------------------------------------------------


def test_merge_windows_overlapping():
    merged = merge_windows(
        [_window(9, 0, 12, 0), _window(11, 0, 15, 0)]
    )
    assert [(w.start, w.end) for w in merged] == [
        (
            parse_time_on_date(MONDAY, time(9, 0), KOLKATA),
            parse_time_on_date(MONDAY, time(15, 0), KOLKATA),
        )
    ]


def test_merge_windows_touching_merges():
    merged = merge_windows(
        [_window(9, 0, 12, 0), _window(12, 0, 15, 0)]
    )
    assert len(merged) == 1
    assert merged[0].end == parse_time_on_date(MONDAY, time(15, 0), KOLKATA)


def test_merge_windows_disjoint_kept():
    merged = merge_windows(
        [_window(9, 0, 10, 0), _window(11, 0, 12, 0)]
    )
    assert len(merged) == 2


def test_merge_windows_unsorted_input():
    merged = merge_windows(
        [_window(11, 0, 12, 0), _window(9, 0, 12, 0)]
    )
    assert len(merged) == 1
    assert merged[0].start == parse_time_on_date(MONDAY, time(9, 0), KOLKATA)


# ---------------------------------------------------------------------------
# subtract_windows
# ---------------------------------------------------------------------------


def test_subtract_partial_block():
    result = subtract_windows(
        [_window(9, 0, 17, 0)],
        [_window(12, 0, 14, 0)],
    )
    assert [(w.start.hour, w.end.hour) for w in result] == [(9, 12), (14, 17)]


def test_subtract_edge_touching_is_noop():
    result = subtract_windows(
        [_window(9, 0, 17, 0)],
        [_window(12, 0, 17, 0)],
    )
    assert [(w.start.hour, w.end.hour) for w in result] == [(9, 12)]


def test_subtract_full_containment():
    result = subtract_windows(
        [_window(9, 0, 17, 0)],
        [_window(10, 0, 16, 0)],
    )
    assert [(w.start.hour, w.end.hour) for w in result] == [(9, 10), (16, 17)]


def test_subtract_no_overlap_keeps_window():
    result = subtract_windows(
        [_window(9, 0, 17, 0)],
        [_window(17, 0, 18, 0)],
    )
    assert len(result) == 1


# ---------------------------------------------------------------------------
# apply_exceptions
# ---------------------------------------------------------------------------


def test_apply_block_full_day():
    windows = [_window(9, 0, 17, 0)]
    result = apply_exceptions(
        windows,
        [ExceptionRule(kind=ExceptionKind.BLOCK_FULL_DAY, date=MONDAY)],
        KOLKATA,
    )
    assert result == []


def test_apply_block_partial():
    windows = [_window(9, 0, 17, 0)]
    result = apply_exceptions(
        windows,
        [
            ExceptionRule(
                kind=ExceptionKind.BLOCK_PARTIAL,
                date=MONDAY,
                start_time=time(12, 0),
                end_time=time(14, 0),
            )
        ],
        KOLKATA,
    )
    assert [(w.start.hour, w.end.hour) for w in result] == [(9, 12), (14, 17)]


def test_apply_add_window_on_empty_day():
    windows = [_window(9, 0, 10, 0)]
    tuesday = date(2026, 8, 11)
    result = apply_exceptions(
        windows,
        [
            ExceptionRule(
                kind=ExceptionKind.ADD_WINDOW,
                date=tuesday,
                start_time=time(10, 0),
                end_time=time(11, 0),
            )
        ],
        KOLKATA,
    )
    assert len(result) == 2
    added = [w for w in result if w.start.date() == tuesday]
    assert len(added) == 1
    assert (added[0].start.hour, added[0].end.hour) == (10, 11)


def test_apply_exceptions_block_overrides_add():
    windows = [_window(9, 0, 17, 0)]
    result = apply_exceptions(
        windows,
        [
            ExceptionRule(
                kind=ExceptionKind.ADD_WINDOW,
                date=MONDAY,
                start_time=time(13, 0),
                end_time=time(13, 30),
            ),
            ExceptionRule(
                kind=ExceptionKind.BLOCK_PARTIAL,
                date=MONDAY,
                start_time=time(12, 0),
                end_time=time(14, 0),
            ),
        ],
        KOLKATA,
    )
    # The added 13:00-13:30 window lies inside the blocked 12:00-14:00 span and
    # must NOT survive: a block always overrides an added window, regardless of
    # input order.
    assert [(w.start.hour, w.end.hour) for w in result] == [(9, 12), (14, 17)]


def test_apply_exception_outside_range_is_ignored():
    windows = [_window(9, 0, 17, 0)]
    other_day = date(2026, 8, 12)  # Wednesday — not in the windows
    result = apply_exceptions(
        windows,
        [
            ExceptionRule(
                kind=ExceptionKind.BLOCK_PARTIAL,
                date=other_day,
                start_time=time(9, 0),
                end_time=time(12, 0),
            )
        ],
        KOLKATA,
    )
    assert len(result) == 1


# ---------------------------------------------------------------------------
# DST: parse_time_on_date (ADRs 005-006)
# ---------------------------------------------------------------------------


def test_dst_spring_forward_nonexistent_time():
    dt = parse_time_on_date(SUNDAY_SPRING, time(1, 30), LONDON)
    assert dt.utcoffset() == timedelta(0)  # pre-gap offset (GMT)
    assert dt.astimezone(UTC) == datetime_utc(2026, 3, 29, 1, 30)


def test_dst_autumn_back_fold_zero_is_first_occurrence():
    dt = parse_time_on_date(SUNDAY_AUTUMN, time(1, 30), LONDON, fold=0)
    assert dt.utcoffset() == timedelta(hours=1)  # BST
    assert dt.astimezone(UTC) == datetime_utc(2026, 10, 25, 0, 30)


def test_dst_autumn_back_fold_one_is_second_occurrence():
    dt = parse_time_on_date(SUNDAY_AUTUMN, time(1, 30), LONDON, fold=1)
    assert dt.utcoffset() == timedelta(0)  # GMT
    assert dt.astimezone(UTC) == datetime_utc(2026, 10, 25, 1, 30)


# ---------------------------------------------------------------------------
# DST: window crossing the spring-forward gap (ADR-003 amendment)
# ---------------------------------------------------------------------------


def test_generate_spring_forward_window_has_no_phantom_or_duplicate():
    """A 00:30-03:00 London window on the spring-forward day is 1.5 real hours:
    3 x 30-min meetings, monotonic in UTC, no duplicated intervals."""
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[
            _rule(DayOfWeek.SUNDAY, time(0, 30), time(3, 0)),
        ],
        start_date=SUNDAY_SPRING,
        end_date=SUNDAY_SPRING,
        timezone="Europe/London",
    )
    assert len(slots) == 3

    utc_starts = [s.start_at.astimezone(UTC) for s in slots]
    assert utc_starts == [
        datetime_utc(2026, 3, 29, 0, 30),
        datetime_utc(2026, 3, 29, 1, 0),
        datetime_utc(2026, 3, 29, 1, 30),
    ]
    # Monotonic in UTC and no duplicated intervals.
    assert utc_starts == sorted(utc_starts)
    intervals = {(s.start_at.astimezone(UTC), s.end_at.astimezone(UTC)) for s in slots}
    assert len(intervals) == 3

    # Local display jumps over the gap exactly as the wall clock does: the
    # 01:00 UTC candidate IS the transition instant, displayed as 02:00 BST.
    assert [(s.start_at.hour, s.start_at.minute) for s in slots] == [
        (0, 30),
        (2, 0),
        (2, 30),
    ]
    assert [s.start_at.utcoffset() for s in slots] == [
        timedelta(0),
        timedelta(hours=1),
        timedelta(hours=1),
    ]


# ---------------------------------------------------------------------------
# DST: window spanning the autumn-back fold
# ---------------------------------------------------------------------------


def test_generate_autumn_back_window_keeps_both_occurrences():
    """A 00:30-03:00 London window on the autumn-back day is 3.5 real hours:
    7 x 30-min meetings; the repeated local wall times are distinct UTC instants."""
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[
            _rule(DayOfWeek.SUNDAY, time(0, 30), time(3, 0)),
        ],
        start_date=SUNDAY_AUTUMN,
        end_date=SUNDAY_AUTUMN,
        timezone="Europe/London",
    )
    assert len(slots) == 7

    utc_starts = [s.start_at.astimezone(UTC) for s in slots]
    assert utc_starts == [
        datetime_utc(2026, 10, 24, 23, 30),
        datetime_utc(2026, 10, 25, 0, 0),
        datetime_utc(2026, 10, 25, 0, 30),
        datetime_utc(2026, 10, 25, 1, 0),
        datetime_utc(2026, 10, 25, 1, 30),
        datetime_utc(2026, 10, 25, 2, 0),
        datetime_utc(2026, 10, 25, 2, 30),
    ]
    assert utc_starts == sorted(utc_starts)
    intervals = {(s.start_at.astimezone(UTC), s.end_at.astimezone(UTC)) for s in slots}
    assert len(intervals) == 7

    # Both "01:30" local occurrences exist, as distinct instants with distinct offsets.
    one_thirties = [s for s in slots if (s.start_at.hour, s.start_at.minute) == (1, 30)]
    assert len(one_thirties) == 2
    assert {s.start_at.utcoffset() for s in one_thirties} == {
        timedelta(hours=1),  # BST (first occurrence)
        timedelta(0),  # GMT (second occurrence)
    }


# ---------------------------------------------------------------------------
# Timezone conversion
# ---------------------------------------------------------------------------


def test_timezone_conversion_kolkata():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert slots[0].start_at.astimezone(UTC) == datetime_utc(2026, 8, 10, 3, 30)
    assert slots[0].start_at.hour == 9  # local wall clock
    assert slots[-1].end_at.astimezone(UTC) == datetime_utc(2026, 8, 10, 6, 30)


# ---------------------------------------------------------------------------
# Buffers and collision primitives (ADR-004, ADR-008)
# ---------------------------------------------------------------------------


def test_occupied_interval_includes_buffers():
    spec = _spec(duration_minutes=30, buffer_before_minutes=5, buffer_after_minutes=10)
    candidate = SlotCandidate(
        start_at=parse_time_on_date(MONDAY, time(9, 5), KOLKATA),
        end_at=parse_time_on_date(MONDAY, time(9, 35), KOLKATA),
    )
    occ = occupied(candidate, spec)
    assert occ.start == parse_time_on_date(MONDAY, time(9, 0), KOLKATA)
    assert occ.end == parse_time_on_date(MONDAY, time(9, 45), KOLKATA)


def test_overlaps_booked_disjoint():
    spec = _spec(duration_minutes=30)
    candidate = SlotCandidate(
        start_at=parse_time_on_date(MONDAY, time(9, 0), KOLKATA),
        end_at=parse_time_on_date(MONDAY, time(9, 30), KOLKATA),
    )
    booked = TimeWindow(
        start=parse_time_on_date(MONDAY, time(10, 0), KOLKATA),
        end=parse_time_on_date(MONDAY, time(10, 30), KOLKATA),
    )
    assert overlaps_booked(candidate, spec, booked) is False


def test_overlaps_booked_with_buffers_overlaps():
    spec = _spec(duration_minutes=30, buffer_before_minutes=5, buffer_after_minutes=10)
    candidate = SlotCandidate(
        start_at=parse_time_on_date(MONDAY, time(9, 45), KOLKATA),
        end_at=parse_time_on_date(MONDAY, time(10, 15), KOLKATA),
    )
    # Occupied interval is 09:40-10:25; the booked 10:00-10:30 overlaps it.
    booked = TimeWindow(
        start=parse_time_on_date(MONDAY, time(10, 0), KOLKATA),
        end=parse_time_on_date(MONDAY, time(10, 30), KOLKATA),
    )
    assert overlaps_booked(candidate, spec, booked) is True


def test_overlaps_booked_touching_is_allowed():
    spec = _spec(duration_minutes=30, buffer_before_minutes=5, buffer_after_minutes=10)
    candidate = SlotCandidate(
        start_at=parse_time_on_date(MONDAY, time(9, 5), KOLKATA),
        end_at=parse_time_on_date(MONDAY, time(9, 35), KOLKATA),
    )
    # Candidate occupied ends at 09:45; booked starts at 09:45 — touching, not overlap.
    booked = TimeWindow(
        start=parse_time_on_date(MONDAY, time(9, 45), KOLKATA),
        end=parse_time_on_date(MONDAY, time(10, 15), KOLKATA),
    )
    assert overlaps_booked(candidate, spec, booked) is False


def test_exclude_overlapping_booked_filters():
    spec = _spec(duration_minutes=30)
    engine = SlotGenerationEngine()
    candidates = engine.generate(
        event_type=spec,
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    booked = [
        TimeWindow(
            start=parse_time_on_date(MONDAY, time(10, 0), KOLKATA),
            end=parse_time_on_date(MONDAY, time(10, 30), KOLKATA),
        )
    ]
    remaining = exclude_overlapping_booked(candidates, spec, booked)
    assert len(remaining) == 5
    assert all(c.start_at != parse_time_on_date(MONDAY, time(10, 0), KOLKATA) for c in remaining)


# ---------------------------------------------------------------------------
# Boundaries and validation
# ---------------------------------------------------------------------------


def test_zero_length_window_dropped():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[_rule(DayOfWeek.MONDAY, time(12, 0), time(12, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert slots == []


def test_end_before_start_window_dropped():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[_rule(DayOfWeek.MONDAY, time(12, 0), time(9, 0))],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert slots == []


def test_start_date_after_end_date_raises():
    with pytest.raises(ValueError):
        SlotGenerationEngine().generate(
            event_type=_spec(duration_minutes=30),
            availability=[_rule(DayOfWeek.MONDAY)],
            start_date=date(2026, 8, 12),
            end_date=date(2026, 8, 10),
            timezone="Asia/Kolkata",
        )


def test_generate_accepts_exceptions_kwarg():
    slots = SlotGenerationEngine().generate(
        event_type=_spec(duration_minutes=30),
        availability=[_rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0))],
        exceptions=[
            ExceptionRule(
                kind=ExceptionKind.BLOCK_PARTIAL,
                date=MONDAY,
                start_time=time(10, 0),
                end_time=time(10, 30),
            )
        ],
        start_date=MONDAY,
        end_date=MONDAY,
        timezone="Asia/Kolkata",
    )
    assert len(slots) == 5  # 10:00-10:30 candidate blocked, 6 - 1
    assert all(s.start_at != parse_time_on_date(MONDAY, time(10, 0), KOLKATA) for s in slots)


def test_split_into_slots_returns_candidates():
    spec = _spec(duration_minutes=30)
    window = _window(9, 0, 12, 0)
    candidates = split_into_slots(window, spec)
    assert len(candidates) == 6
    assert all(isinstance(c, SlotCandidate) for c in candidates)


def test_windows_for_weekday_rule_returns_aware_windows():
    windows = windows_for_weekday_rule(
        _rule(DayOfWeek.MONDAY, time(9, 0), time(12, 0)),
        MONDAY,
        MONDAY,
        KOLKATA,
    )
    assert len(windows) == 1
    assert windows[0].start.tzinfo is not None
    assert windows[0].end.tzinfo is not None


def datetime_utc(year: int, month: int, day: int, hour: int, minute: int):
    from datetime import datetime

    return datetime(year, month, day, hour, minute, tzinfo=UTC)
