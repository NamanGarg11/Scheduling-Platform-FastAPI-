"""Pure slot-generation engine (Phase S1).

This module contains **only interval mathematics**: inputs in, calculated
intervals out. It has no knowledge of:

- SQLAlchemy / PostgreSQL / AsyncSession
- repositories
- FastAPI / HTTP
- the clock (no datetime.now / utcnow / date.today)

All timezone handling happens here via ``zoneinfo`` (ADRs 005-007), and slot
stepping is anchored in UTC (ADR-003 amendment). See ``docs/DECISIONS.md`` and
``docs/S1_SLOT_GENERATION_SPEC.md`` for the normative contracts.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo

from app.availability.enums import DayOfWeek


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """Half-open interval [start, end) with aware datetimes in a single zone."""

    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class EventTypeSpec:
    """Pure projection of an EventType (duration + buffers)."""

    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int


@dataclass(frozen=True, slots=True)
class AvailabilityRule:
    """Pure projection of a weekly Availability row."""

    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    is_available: bool


class ExceptionKind(Enum):
    BLOCK_FULL_DAY = "BLOCK_FULL_DAY"
    BLOCK_PARTIAL = "BLOCK_PARTIAL"
    ADD_WINDOW = "ADD_WINDOW"


@dataclass(frozen=True, slots=True)
class ExceptionRule:
    """Pure availability exception (S2 persists these; S1 only computes with them)."""

    kind: ExceptionKind
    date: date
    start_time: time | None = None  # required for BLOCK_PARTIAL / ADD_WINDOW
    end_time: time | None = None


@dataclass(frozen=True, slots=True)
class SlotCandidate:
    """A meeting interval, aware datetimes in the host's local zone."""

    start_at: datetime
    end_at: datetime


def parse_time_on_date(
    d: date,
    t: time,
    tz: ZoneInfo,
    *,
    fold: int = 0,
) -> datetime:
    """Combine a calendar date and wall time in ``tz``.

    The single DST resolution point (ADRs 005-006):

    - Nonexistent local times (spring-forward gap) resolve to the pre-gap offset,
      i.e. the UTC instant the wall clock would have reached absent the jump
      (equivalently, the wall time shifts forward by the gap).
    - Ambiguous local times (autumn-back) resolve with the explicit ``fold``;
      the engine always uses ``fold=0`` (first occurrence, DST).

    ``fold`` must be set on the ``time`` argument because ``datetime.combine``
    does not accept it.
    """
    return datetime.combine(d, t.replace(fold=fold), tzinfo=tz)


def _weekday_of(d: date) -> DayOfWeek:
    return DayOfWeek(d.strftime("%A").upper())


def windows_for_weekday_rule(
    rule: AvailabilityRule,
    start_date: date,
    end_date: date,
    tz: ZoneInfo,
) -> list[TimeWindow]:
    """Expand a weekly rule into concrete windows over ``[start_date, end_date]``.

    Only matching weekdays with ``is_available`` contribute. Windows with
    ``end <= start`` are dropped.
    """
    windows: list[TimeWindow] = []
    current = start_date
    while current <= end_date:
        if rule.is_available and _weekday_of(current) == rule.day_of_week:
            start = parse_time_on_date(current, rule.start_time, tz)
            end = parse_time_on_date(current, rule.end_time, tz)
            if end > start:
                windows.append(TimeWindow(start=start, end=end))
        current += timedelta(days=1)
    return windows


def merge_windows(windows: list[TimeWindow]) -> list[TimeWindow]:
    """Sort and merge windows; touching windows merge (ADR-002)."""
    if not windows:
        return []
    ordered = sorted(windows, key=lambda w: (w.start, w.end))
    merged: list[TimeWindow] = [ordered[0]]
    for window in ordered[1:]:
        last = merged[-1]
        if window.start <= last.end:
            if window.end > last.end:
                merged[-1] = TimeWindow(start=last.start, end=window.end)
        else:
            merged.append(window)
    return merged


def subtract_windows(
    windows: list[TimeWindow],
    blocked: list[TimeWindow],
) -> list[TimeWindow]:
    """Remove half-open blocked intervals from windows; result is sorted/merged."""
    remaining: list[TimeWindow] = []
    for window in windows:
        pieces = [window]
        for block in blocked:
            next_pieces: list[TimeWindow] = []
            for piece in pieces:
                if block.end <= piece.start or block.start >= piece.end:
                    next_pieces.append(piece)
                    continue
                if block.start > piece.start:
                    next_pieces.append(TimeWindow(start=piece.start, end=block.start))
                if block.end < piece.end:
                    next_pieces.append(TimeWindow(start=block.end, end=piece.end))
            pieces = next_pieces
        remaining.extend(pieces)
    return merge_windows(remaining)


def _exception_window(exc: ExceptionRule, tz: ZoneInfo) -> TimeWindow | None:
    if exc.start_time is None or exc.end_time is None:
        return None
    start = parse_time_on_date(exc.date, exc.start_time, tz)
    end = parse_time_on_date(exc.date, exc.end_time, tz)
    if end <= start:
        return None
    return TimeWindow(start=start, end=end)


def apply_exceptions(
    windows: list[TimeWindow],
    exceptions: list[ExceptionRule],
    tz: ZoneInfo,
) -> list[TimeWindow]:
    """Apply exceptions; a block always overrides an added window.

    Implemented by applying ``ADD_WINDOW`` first, then blocks: an added window
    that falls inside a blocked span is removed by the block, so a block never
    gets resurrected by an add (order of the input list is irrelevant).

    Exceptions override availability rules. ``ADD_WINDOW`` can create
    availability on an otherwise-empty day; a ``BLOCK_*`` on an empty date is a
    no-op. Exceptions on dates outside the windows are harmless no-ops.
    """
    result = list(windows)
    for exc in exceptions:
        if exc.kind == ExceptionKind.ADD_WINDOW:
            added = _exception_window(exc, tz)
            if added is not None:
                result.append(added)
    result = merge_windows(result)
    for exc in exceptions:
        if exc.kind == ExceptionKind.BLOCK_FULL_DAY:
            result = [
                w
                for w in result
                if w.start.date() != exc.date and w.end.date() != exc.date
            ]
        elif exc.kind == ExceptionKind.BLOCK_PARTIAL:
            block = _exception_window(exc, tz)
            if block is not None:
                result = subtract_windows(result, [block])
    return merge_windows(result)


def split_into_slots(
    window: TimeWindow,
    spec: EventTypeSpec,
) -> list[SlotCandidate]:
    """Split a window into meeting candidates (ADR-003).

    Stepping is anchored in UTC (ADR-003 amendment): the window is converted to
    UTC instants, the cursor advances by the occupied duration, and each
    candidate is converted back to the window's local zone. On days without a
    DST transition this is identical to wall-clock stepping; across a
    spring-forward gap it prevents the cursor from folding back onto earlier
    UTC intervals.
    """
    utc_start = window.start.astimezone(timezone.utc)
    utc_end = window.end.astimezone(timezone.utc)
    before = timedelta(minutes=spec.buffer_before_minutes)
    duration = timedelta(minutes=spec.duration_minutes)
    occupied = before + duration + timedelta(minutes=spec.buffer_after_minutes)
    local_tz = window.start.tzinfo

    candidates: list[SlotCandidate] = []
    cursor = utc_start
    while cursor + occupied <= utc_end:
        actual_start = cursor + before
        actual_end = actual_start + duration
        candidates.append(
            SlotCandidate(
                start_at=actual_start.astimezone(local_tz),
                end_at=actual_end.astimezone(local_tz),
            )
        )
        cursor += occupied
    return candidates


def occupied(
    candidate: SlotCandidate,
    spec: EventTypeSpec,
) -> TimeWindow:
    """The candidate's collision interval [start - before, end + after) (ADR-004).

    Returned as UTC instants: the collision domain is real time, not wall clock.
    """
    return TimeWindow(
        start=candidate.start_at.astimezone(timezone.utc)
        - timedelta(minutes=spec.buffer_before_minutes),
        end=candidate.end_at.astimezone(timezone.utc)
        + timedelta(minutes=spec.buffer_after_minutes),
    )


def overlaps_booked(
    candidate: SlotCandidate,
    spec: EventTypeSpec,
    booked: TimeWindow,
) -> bool:
    """Half-open overlap between the candidate's occupied interval and a booked
    interval (ADRs 004, 008). Touching is allowed.
    """
    candidate_occupied = occupied(candidate, spec)
    return (
        candidate_occupied.start < booked.end
        and booked.start < candidate_occupied.end
    )


def exclude_overlapping_booked(
    candidates: list[SlotCandidate],
    spec: EventTypeSpec,
    booked_windows: list[TimeWindow],
) -> list[SlotCandidate]:
    """Keep only candidates whose occupied interval overlaps no booked window."""
    return [
        candidate
        for candidate in candidates
        if not any(overlaps_booked(candidate, spec, booked) for booked in booked_windows)
    ]


class SlotGenerationEngine:
    """Pure scheduling engine.

    Converts event-type spec + availability rules + exceptions + date range into
    ``SlotCandidate`` objects. Inputs are duck-typed: ORM models exposing the
    same attributes (``duration_minutes``, ``buffer_*_minutes``,
    ``day_of_week``/``start_time``/``end_time``/``is_available``) are accepted so
    the orchestrator can pass them without mapping; the pure dataclasses are the
    canonical types.
    """

    def generate(
        self,
        *,
        event_type: EventTypeSpec,
        availability: list[AvailabilityRule],
        start_date: date,
        end_date: date,
        timezone: str,
        exceptions: list[ExceptionRule] | None = None,
    ) -> list[SlotCandidate]:
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date.")

        tz = ZoneInfo(timezone)

        windows: list[TimeWindow] = []
        for rule in availability:
            windows.extend(windows_for_weekday_rule(rule, start_date, end_date, tz))

        windows = merge_windows(windows)
        windows = apply_exceptions(windows, exceptions or [], tz)
        windows = merge_windows(windows)

        candidates: list[SlotCandidate] = []
        for window in windows:
            candidates.extend(split_into_slots(window, event_type))
        return candidates
