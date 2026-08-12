"""Service-layer tests for host-wide slot regeneration (S2-B).

Repositories are mocked; the real S1 engine runs underneath. The clock is
frozen so date-dependent behavior (default range, DST resolution) is
deterministic.
"""

from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.availability.enums import DayOfWeek
from app.availability.exceptions.enums import AvailabilityExceptionKind
from app.availability.exceptions.model import AvailabilityException
from app.availability.exceptions.repository import AvailabilityExceptionRepository
from app.availability.model import Availability
from app.availability.repository import AvailabilityRepository
from app.core.exceptions.base import NotFoundException, ValidationException
from app.event_types.model import EventType
from app.event_types.repository import EventTypeRepository
from app.slots.enums import SlotStatus
from app.slots.model import Slot
from app.slots.repository import SlotRepository
from app.slots.service import SLOT_GENERATION_DAYS, SlotService
from app.slots.slot_generation import SlotGenerationEngine
from app.users.model import User
from app.users.repository import UserRepository

UTC = timezone.utc
MONDAY = date(2026, 8, 10)  # a Monday


class FrozenDatetime:
    """Stub for ``datetime`` inside the slot service: fixed ``now``, real ``combine``."""

    FIXED = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.FIXED.astimezone(tz) if tz is not None else cls.FIXED

    @classmethod
    def combine(cls, d, t, *args, **kwargs):
        return datetime.combine(d, t, *args, **kwargs)


def make_host(*, timezone: str = "UTC", host_id: UUID | None = None) -> User:
    return User(
        id=host_id or uuid4(),
        name="Host",
        email=f"host-{uuid4().hex}@example.com",
        slug=f"host-{uuid4().hex}",
        timezone=timezone,
    )


def make_event_type(
    host_id: UUID,
    *,
    duration_minutes: int = 30,
    buffer_before_minutes: int = 0,
    buffer_after_minutes: int = 0,
    is_active: bool = True,
    et_id: UUID | None = None,
) -> EventType:
    return EventType(
        id=et_id or uuid4(),
        host_id=host_id,
        title="Consultation",
        slug=f"et-{uuid4().hex}",
        duration_minutes=duration_minutes,
        is_active=is_active,
        location_type="zoom",
        buffer_before_minutes=buffer_before_minutes,
        buffer_after_minutes=buffer_after_minutes,
    )


def make_availability(
    day: DayOfWeek,
    start_time: time = time(9, 0),
    end_time: time = time(12, 0),
) -> Availability:
    return Availability(
        host_id=uuid4(),
        day_of_week=day,
        start_time=start_time,
        end_time=end_time,
        is_available=True,
    )


def make_exception(
    kind: AvailabilityExceptionKind,
    exception_date: date,
    start_time: time | None = None,
    end_time: time | None = None,
) -> AvailabilityException:
    return AvailabilityException(
        host_id=uuid4(),
        exception_date=exception_date,
        kind=kind,
        start_time=start_time,
        end_time=end_time,
    )


def make_slot(
    host_id: UUID,
    event_type_id: UUID,
    start_at: datetime,
    end_at: datetime,
    status: SlotStatus,
    slot_id: UUID | None = None,
) -> Slot:
    return Slot(
        id=slot_id or uuid4(),
        host_id=host_id,
        event_type_id=event_type_id,
        start_at=start_at,
        end_at=end_at,
        status=status,
    )


def utc(y: int, m: int, d: int, h: int, minute: int = 0) -> datetime:
    return datetime(y, m, d, h, minute, tzinfo=UTC)


class Repos:
    def __init__(self) -> None:
        self.slot = AsyncMock(spec=SlotRepository)
        self.event_type = AsyncMock(spec=EventTypeRepository)
        self.availability = AsyncMock(spec=AvailabilityRepository)
        self.exception = AsyncMock(spec=AvailabilityExceptionRepository)
        self.user = AsyncMock(spec=UserRepository)


def build_service(
    monkeypatch,
    *,
    host: User,
    availability: list[Availability] | None = None,
    exceptions: list[AvailabilityException] | None = None,
    event_types: list[EventType] | None = None,
    existing_slots: list[Slot] | None = None,
    booked_slots: list[Slot] | None = None,
    insert_count: int = 0,
    conditional_counts: tuple[int, int] = (0, 0),
) -> tuple[SlotService, Repos]:
    monkeypatch.setattr("app.slots.service.datetime", FrozenDatetime)

    repos = Repos()
    repos.user.find_by_id = AsyncMock(return_value=host)
    repos.availability.find_week_schedule = AsyncMock(return_value=availability or [])
    repos.exception.find_for_host_and_range = AsyncMock(return_value=exceptions or [])
    repos.event_type.list_by_host = AsyncMock(return_value=event_types or [])
    repos.slot.find_by_host_starting_in_range = AsyncMock(
        return_value=existing_slots or [],
    )
    repos.slot.find_booked_by_host_in_range = AsyncMock(
        return_value=booked_slots or [],
    )
    repos.slot.insert_many_on_conflict_do_nothing = AsyncMock(
        return_value=insert_count,
    )
    repos.slot.set_status_conditional = AsyncMock(
        side_effect=list(conditional_counts),
    )

    service = SlotService(
        slot_repository=repos.slot,
        event_type_repository=repos.event_type,
        availability_repository=repos.availability,
        availability_exception_repository=repos.exception,
        user_repository=repos.user,
        generation_engine=SlotGenerationEngine(),
    )
    return service, repos


async def test_regenerate_default_range_is_30_host_days(monkeypatch):
    host = make_host()
    service, repos = build_service(monkeypatch, host=host)

    response = await service.regenerate_host_slots(host.id)

    assert response.from_date == date(2026, 8, 1)
    assert response.to_date == date(2026, 8, 30)
    assert (response.to_date - response.from_date).days == SLOT_GENERATION_DAYS - 1

    repos.exception.find_for_host_and_range.assert_awaited_with(
        host.id,
        date(2026, 8, 1),
        date(2026, 8, 30),
    )
    repos.slot.find_by_host_starting_in_range.assert_awaited_with(
        host_id=host.id,
        start_at=utc(2026, 8, 1, 0),
        end_at=utc(2026, 8, 31, 0),
    )


async def test_regenerate_explicit_range(monkeypatch):
    host = make_host()
    service, repos = build_service(monkeypatch, host=host)

    response = await service.regenerate_host_slots(
        host.id,
        MONDAY,
        MONDAY,
    )

    assert response.from_date == MONDAY
    assert response.to_date == MONDAY
    assert response.timezone == "UTC"
    repos.slot.find_by_host_starting_in_range.assert_awaited_with(
        host_id=host.id,
        start_at=utc(2026, 8, 10, 0),
        end_at=utc(2026, 8, 11, 0),
    )


async def test_regenerate_range_converted_to_utc_for_host_timezone(monkeypatch):
    host = make_host(timezone="Asia/Kolkata")  # UTC+5:30
    service, repos = build_service(monkeypatch, host=host)

    await service.regenerate_host_slots(host.id, MONDAY, MONDAY)

    # 2026-08-10 00:00 IST = 2026-08-09 18:30 UTC; 2026-08-11 00:00 IST = 2026-08-10 18:30 UTC.
    repos.slot.find_by_host_starting_in_range.assert_awaited_with(
        host_id=host.id,
        start_at=utc(2026, 8, 9, 18, 30),
        end_at=utc(2026, 8, 10, 18, 30),
    )


async def test_regenerate_dst_spring_forward_range(monkeypatch):
    host = make_host(timezone="Europe/London")
    service, repos = build_service(monkeypatch, host=host)

    await service.regenerate_host_slots(
        host.id,
        date(2026, 3, 29),  # spring-forward day
        date(2026, 3, 29),
    )

    # 2026-03-29 00:00 GMT = 00:00 UTC; 2026-03-30 00:00 BST = 2026-03-29 23:00 UTC.
    # The range correctly spans 23 real hours across the gap (ADR-009).
    repos.slot.find_by_host_starting_in_range.assert_awaited_with(
        host_id=host.id,
        start_at=utc(2026, 3, 29, 0),
        end_at=utc(2026, 3, 29, 23),
    )


async def test_regenerate_host_missing_raises_404(monkeypatch):
    host = make_host()
    service, repos = build_service(monkeypatch, host=host)
    repos.user.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException) as exc_info:
        await service.regenerate_host_slots(host.id)
    assert exc_info.value.status_code == 404


async def test_regenerate_from_after_to_raises_400(monkeypatch):
    host = make_host()
    service, _ = build_service(monkeypatch, host=host)

    with pytest.raises(ValidationException) as exc_info:
        await service.regenerate_host_slots(
            host.id,
            date(2026, 8, 11),
            date(2026, 8, 10),
        )
    assert exc_info.value.status_code == 400


async def test_regenerate_reconciles_all_branches(monkeypatch):
    host = make_host()
    host_id = host.id
    et = make_event_type(host_id)
    service, repos = build_service(
        monkeypatch,
        host=host,
        availability=[make_availability(DayOfWeek.MONDAY)],
        event_types=[et],
        existing_slots=[
            make_slot(host_id, et.id, utc(2026, 8, 10, 9), utc(2026, 8, 10, 9, 30), SlotStatus.AVAILABLE),  # kept
            make_slot(host_id, et.id, utc(2026, 8, 10, 9, 30), utc(2026, 8, 10, 10), SlotStatus.BLOCKED),  # restored
            make_slot(host_id, et.id, utc(2026, 8, 10, 10), utc(2026, 8, 10, 10, 30), SlotStatus.BOOKED),  # untouched
            make_slot(host_id, et.id, utc(2026, 8, 10, 12), utc(2026, 8, 10, 12, 30), SlotStatus.AVAILABLE),  # blocked
            make_slot(host_id, et.id, utc(2026, 8, 10, 13), utc(2026, 8, 10, 13, 30), SlotStatus.BOOKED),  # untouched
        ],
        insert_count=3,
        conditional_counts=(1, 1),
    )

    response = await service.regenerate_host_slots(host.id, MONDAY, MONDAY)

    assert response.generated_count == 3
    assert response.restored_count == 1
    assert response.blocked_count == 1
    assert response.kept_count == 1
    assert response.booked_count == 2

    # Candidates generated: 09:00..11:30 (6 x 30min). Existing: 09:00 kept,
    # 09:30 restored, 10:00 booked. Missing: 10:30, 11:00, 11:30 -> inserted.
    inserted = repos.slot.insert_many_on_conflict_do_nothing.await_args.args[0]
    assert len(inserted) == 3
    assert {s.start_at for s in inserted} == {
        utc(2026, 8, 10, 10, 30),
        utc(2026, 8, 10, 11),
        utc(2026, 8, 10, 11, 30),
    }

    calls = repos.slot.set_status_conditional.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == SlotStatus.AVAILABLE  # restore
    assert calls[1].args[1] == SlotStatus.BLOCKED  # block


async def test_regenerate_applies_exceptions(monkeypatch):
    host = make_host()
    host_id = host.id
    et = make_event_type(host_id)
    service, repos = build_service(
        monkeypatch,
        host=host,
        availability=[make_availability(DayOfWeek.MONDAY)],
        exceptions=[
            make_exception(
                AvailabilityExceptionKind.BLOCK_PARTIAL,
                MONDAY,
                time(10, 0),
                time(11, 0),
            )
        ],
        event_types=[et],
        insert_count=4,
    )

    await service.regenerate_host_slots(host.id, MONDAY, MONDAY)

    inserted = repos.slot.insert_many_on_conflict_do_nothing.await_args.args[0]
    assert {s.start_at for s in inserted} == {
        utc(2026, 8, 10, 9),
        utc(2026, 8, 10, 9, 30),
        utc(2026, 8, 10, 11),
        utc(2026, 8, 10, 11, 30),
    }


async def test_regenerate_inactive_event_type_skipped(monkeypatch):
    host = make_host()
    host_id = host.id
    et = make_event_type(host_id, is_active=False)
    service, repos = build_service(
        monkeypatch,
        host=host,
        availability=[make_availability(DayOfWeek.MONDAY)],
        event_types=[et],
    )

    response = await service.regenerate_host_slots(host.id, MONDAY, MONDAY)

    assert response.generated_count == 0
    repos.slot.insert_many_on_conflict_do_nothing.assert_awaited_with([])


async def test_regenerate_booked_collision_excludes_other_event_type(monkeypatch):
    host = make_host()
    host_id = host.id
    et_a = make_event_type(
        host_id,
        buffer_before_minutes=5,
        buffer_after_minutes=10,
    )
    et_b = make_event_type(host_id)
    booked = make_slot(
        host_id,
        et_a.id,
        utc(2026, 8, 10, 10),
        utc(2026, 8, 10, 10, 30),
        SlotStatus.BOOKED,
    )
    service, repos = build_service(
        monkeypatch,
        host=host,
        availability=[make_availability(DayOfWeek.MONDAY)],
        event_types=[et_a, et_b],
        existing_slots=[booked],
        booked_slots=[booked],
        insert_count=6,
    )

    await service.regenerate_host_slots(host.id, MONDAY, MONDAY)

    inserted = repos.slot.insert_many_on_conflict_do_nothing.await_args.args[0]
    inserted_keys = {(s.event_type_id, s.start_at) for s in inserted}

    # et_a's 10:00 candidate is excluded by collision with its own booked
    # occupancy [09:55, 10:40) (before=5, after=10) -> never inserted.
    assert (et_a.id, utc(2026, 8, 10, 10)) not in inserted_keys
    # et_b's 10:00 and 09:30 candidates overlap [09:55, 10:40) -> excluded
    # (ADR-008: a booking's buffers protect against other event types too).
    assert (et_b.id, utc(2026, 8, 10, 10)) not in inserted_keys
    assert (et_b.id, utc(2026, 8, 10, 9, 30)) not in inserted_keys
    # et_b's 09:00 candidate: occupied [09:00,09:30) vs [09:55,10:40) -> disjoint.
    assert (et_b.id, utc(2026, 8, 10, 9)) in inserted_keys


async def test_regenerate_booked_slot_never_modified(monkeypatch):
    host = make_host()
    host_id = host.id
    et = make_event_type(host_id)
    booked = make_slot(
        host_id,
        et.id,
        utc(2026, 8, 10, 10),
        utc(2026, 8, 10, 10, 30),
        SlotStatus.BOOKED,
    )
    service, repos = build_service(
        monkeypatch,
        host=host,
        availability=[make_availability(DayOfWeek.MONDAY)],
        event_types=[et],
        existing_slots=[booked],
        booked_slots=[booked],
        insert_count=5,
    )

    response = await service.regenerate_host_slots(host.id, MONDAY, MONDAY)

    assert response.booked_count == 1
    # The booked slot id must never appear in a status change.
    for call in repos.slot.set_status_conditional.await_args_list:
        assert booked.id not in call.args[0]
    assert booked.status == SlotStatus.BOOKED


async def test_regenerate_multiple_event_types_and_buffers(monkeypatch):
    host = make_host()
    host_id = host.id
    et_short = make_event_type(host_id, duration_minutes=30)
    et_long = make_event_type(
        host_id,
        duration_minutes=60,
        buffer_before_minutes=10,
        buffer_after_minutes=15,
    )
    service, repos = build_service(
        monkeypatch,
        host=host,
        availability=[make_availability(DayOfWeek.MONDAY)],
        event_types=[et_short, et_long],
        insert_count=9,
    )

    await service.regenerate_host_slots(host.id, MONDAY, MONDAY)

    inserted = repos.slot.insert_many_on_conflict_do_nothing.await_args.args[0]
    short_count = sum(1 for s in inserted if s.event_type_id == et_short.id)
    long_count = sum(1 for s in inserted if s.event_type_id == et_long.id)
    assert short_count == 6  # 09:00..11:30, 30-min meetings, no buffers
    # occupied = 10 + 60 + 15 = 85 min; cursors 09:00, 10:25, 11:50 -> 2 meetings.
    assert long_count == 2
