"""Service-layer tests for the public slot listing (S3).

Repositories are mocked; the clock is frozen. The focus is the S3-specific
logic: event-type resolution, 62-day validation, UTC range conversion,
AVAILABLE/past filtering, and local-day grouping with UTC timestamps.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.core.exceptions.base import NotFoundException, ValidationException
from app.event_types.model import EventType
from app.event_types.repository import EventTypeRepository
from app.slots.enums import SlotStatus
from app.slots.model import Slot
from app.slots.public_service import (
    MAX_PUBLIC_RANGE_DAYS,
    PublicSlotService,
)
from app.slots.repository import SlotRepository
from app.users.model import User
from app.users.repository import UserRepository

UTC = timezone.utc


class FrozenDatetime:
    """Stub for ``datetime`` in the public service: fixed ``now``, real ``combine``."""

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
    slug: str = "consultation",
    is_active: bool = True,
    et_id: UUID | None = None,
) -> EventType:
    return EventType(
        id=et_id or uuid4(),
        host_id=host_id,
        title="Consultation",
        slug=slug,
        duration_minutes=30,
        is_active=is_active,
        location_type="zoom",
    )


def make_slot(
    event_type_id: UUID,
    start_at: datetime,
    end_at: datetime | None = None,
    status: SlotStatus = SlotStatus.AVAILABLE,
) -> Slot:
    return Slot(
        id=uuid4(),
        host_id=uuid4(),
        event_type_id=event_type_id,
        start_at=start_at,
        end_at=end_at or (start_at + __import__("datetime").timedelta(minutes=30)),
        status=status,
    )


def utc(y: int, m: int, d: int, h: int, minute: int = 0) -> datetime:
    return datetime(y, m, d, h, minute, tzinfo=UTC)


class Repos:
    def __init__(self) -> None:
        self.slot = AsyncMock(spec=SlotRepository)
        self.event_type = AsyncMock(spec=EventTypeRepository)
        self.user = AsyncMock(spec=UserRepository)


def build_service(
    monkeypatch,
    *,
    host: User,
    event_type: EventType,
    slots: list[Slot] | None = None,
) -> tuple[PublicSlotService, Repos]:
    monkeypatch.setattr("app.slots.public_service.datetime", FrozenDatetime)

    repos = Repos()
    repos.user.find_by_id = AsyncMock(return_value=host)
    repos.event_type.find_by_host_and_slug = AsyncMock(return_value=event_type)
    repos.slot.find_available_for_event_type_in_range = AsyncMock(
        return_value=slots or [],
    )

    service = PublicSlotService(
        slot_repository=repos.slot,
        event_type_repository=repos.event_type,
        user_repository=repos.user,
    )
    return service, repos


async def test_default_range_uses_host_calendar_days(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    service, repos = build_service(monkeypatch, host=host, event_type=et)

    response = await service.list_public_slots(host.id, et.slug)

    assert response.timezone == "UTC"
    assert response.days == []
    repos.slot.find_available_for_event_type_in_range.assert_awaited_with(
        event_type_id=et.id,
        start_at=utc(2026, 8, 1, 0),
        end_at=utc(2026, 8, 31, 0),
    )


async def test_explicit_range_converted_to_utc_for_requested_timezone(monkeypatch):
    host = make_host(timezone="Asia/Kolkata")
    et = make_event_type(host.id)
    service, repos = build_service(monkeypatch, host=host, event_type=et)

    await service.list_public_slots(
        host.id,
        et.slug,
        from_date=date(2026, 8, 10),
        to_date=date(2026, 8, 10),
    )

    # 2026-08-10 00:00 IST = 2026-08-09 18:30 UTC; 2026-08-11 00:00 IST = 2026-08-10 18:30 UTC.
    repos.slot.find_available_for_event_type_in_range.assert_awaited_with(
        event_type_id=et.id,
        start_at=utc(2026, 8, 9, 18, 30),
        end_at=utc(2026, 8, 10, 18, 30),
    )


async def test_maximum_range_accepted(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    service, _ = build_service(monkeypatch, host=host, event_type=et)

    response = await service.list_public_slots(
        host.id,
        et.slug,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 1) + __import__("datetime").timedelta(
            days=MAX_PUBLIC_RANGE_DAYS,
        ),
    )
    assert response.days == []


async def test_range_exceeding_62_days_raises_400(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    service, _ = build_service(monkeypatch, host=host, event_type=et)

    with pytest.raises(ValidationException) as exc_info:
        await service.list_public_slots(
            host.id,
            et.slug,
            from_date=date(2026, 8, 1),
            to_date=date(2026, 8, 1) + __import__("datetime").timedelta(
                days=MAX_PUBLIC_RANGE_DAYS + 1,
            ),
        )
    assert exc_info.value.status_code == 400


async def test_from_after_to_raises_400(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    service, _ = build_service(monkeypatch, host=host, event_type=et)

    with pytest.raises(ValidationException) as exc_info:
        await service.list_public_slots(
            host.id,
            et.slug,
            from_date=date(2026, 8, 11),
            to_date=date(2026, 8, 10),
        )
    assert exc_info.value.status_code == 400


async def test_invalid_timezone_raises_400(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    service, _ = build_service(monkeypatch, host=host, event_type=et)

    with pytest.raises(ValidationException) as exc_info:
        await service.list_public_slots(
            host.id,
            et.slug,
            from_date=date(2026, 8, 10),
            to_date=date(2026, 8, 10),
            requested_timezone="Mars/Olympus",
        )
    assert exc_info.value.status_code == 400


async def test_unknown_user_raises_404(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    service, repos = build_service(monkeypatch, host=host, event_type=et)
    repos.user.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException) as exc_info:
        await service.list_public_slots(host.id, et.slug)
    assert exc_info.value.status_code == 404


async def test_unknown_event_type_raises_404(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    service, repos = build_service(monkeypatch, host=host, event_type=et)
    repos.event_type.find_by_host_and_slug = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException) as exc_info:
        await service.list_public_slots(host.id, et.slug)
    assert exc_info.value.status_code == 404


async def test_inactive_event_type_raises_404(monkeypatch):
    host = make_host()
    et = make_event_type(host.id, is_active=False)
    service, _ = build_service(monkeypatch, host=host, event_type=et)

    with pytest.raises(NotFoundException) as exc_info:
        await service.list_public_slots(host.id, et.slug)
    assert exc_info.value.status_code == 404


async def test_filters_past_slots_keeps_future(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    future = make_slot(et.id, utc(2026, 8, 10, 3, 30))  # 09:00 IST
    past = make_slot(et.id, utc(2026, 7, 20, 3, 30))
    service, _ = build_service(
        monkeypatch,
        host=host,
        event_type=et,
        slots=[future, past],
    )

    response = await service.list_public_slots(
        host.id,
        et.slug,
        from_date=date(2026, 8, 10),
        to_date=date(2026, 8, 10),
    )

    assert len(response.days) == 1
    slots = response.days[0].slots
    assert len(slots) == 1
    assert slots[0].start_at == utc(2026, 8, 10, 3, 30)


async def test_grouping_by_local_day_keeps_utc_timestamps(monkeypatch):
    """A slot at 2026-08-09T20:30Z is 02:00 IST on 2026-08-10.

    It must group under 2026-08-10 for Asia/Kolkata, and under 2026-08-09 for
    UTC — while the returned timestamp stays the same UTC instant.
    """
    host = make_host(timezone="Asia/Kolkata")
    et = make_event_type(host.id)
    slot = make_slot(et.id, utc(2026, 8, 9, 20, 30))
    service, _ = build_service(
        monkeypatch,
        host=host,
        event_type=et,
        slots=[slot],
    )

    kolkata = await service.list_public_slots(
        host.id,
        et.slug,
        from_date=date(2026, 8, 9),
        to_date=date(2026, 8, 10),
        requested_timezone="Asia/Kolkata",
    )
    assert [day.date for day in kolkata.days] == [date(2026, 8, 10)]
    assert kolkata.days[0].slots[0].start_at == utc(2026, 8, 9, 20, 30)
    assert kolkata.timezone == "Asia/Kolkata"

    utc_view = await service.list_public_slots(
        host.id,
        et.slug,
        from_date=date(2026, 8, 9),
        to_date=date(2026, 8, 10),
        requested_timezone="UTC",
    )
    assert [day.date for day in utc_view.days] == [date(2026, 8, 9)]
    assert utc_view.days[0].slots[0].start_at == utc(2026, 8, 9, 20, 30)


async def test_empty_availability_returns_empty_days(monkeypatch):
    host = make_host()
    et = make_event_type(host.id)
    service, _ = build_service(monkeypatch, host=host, event_type=et)

    response = await service.list_public_slots(
        host.id,
        et.slug,
        from_date=date(2026, 8, 10),
        to_date=date(2026, 8, 10),
    )

    assert response.days == []
    assert response.event_type.slug == et.slug
    assert response.event_type.title == "Consultation"
