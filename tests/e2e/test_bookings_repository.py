from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import dialect as pg_dialect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.enums import BookingStatus
from app.bookings.model import Booking
from app.bookings.repository import BookingRepository
from app.slots.enums import SlotStatus
from app.slots.model import Slot
from app.users.model import User


@pytest.fixture
async def session(clean_db) -> AsyncSession:
    from app.config.database import SessionLocal

    async with SessionLocal() as s:
        yield s
        await s.rollback()


def slot_window(slot: Slot) -> None:
    base = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
    slot.start_at = base
    slot.end_at = base.replace(hour=9, minute=30)


async def seed_host(session: AsyncSession) -> User:
    host = User(
        name="Repo Host",
        email=f"rh-{uuid4().hex}@example.com",
        slug=f"rh-{uuid4().hex}",
        timezone="UTC",
    )
    session.add(host)
    await session.flush()
    return host


async def seed_event_type(session: AsyncSession, host: User):
    from app.event_types.enums import LocationType
    from app.event_types.model import EventType

    event_type = EventType(
        title=f"Repo Event {uuid4().hex[:8]}",
        slug=f"repo-event-{uuid4().hex[:8]}",
        description=None,
        duration_minutes=30,
        is_active=True,
        location_type=LocationType.ZOOM,
        location_value="https://example.test",
        buffer_before_minutes=0,
        buffer_after_minutes=0,
        host=host,
    )
    session.add(event_type)
    await session.flush()
    return event_type


async def seed_slot(
    session: AsyncSession,
    *,
    status: SlotStatus = SlotStatus.AVAILABLE,
) -> Slot:
    host = await seed_host(session)
    event_type = await seed_event_type(session, host)
    slot = Slot(
        host_id=host.id,
        event_type_id=event_type.id,
        start_at=None,
        end_at=None,
        status=status,
    )
    slot_window(slot)
    session.add(slot)
    await session.flush()
    return slot


def seed_email(email: str | None = None) -> str:
    return email or f"inv-{uuid4().hex}@example.com"


async def seed_booking(
    session: AsyncSession,
    slot: Slot,
    *,
    email: str | None = None,
) -> Booking:
    booking = Booking(
        slot_id=slot.id,
        host_id=slot.host_id,
        event_type_id=slot.event_type_id,
        invitee_email=seed_email(email),
        invitee_name="Repo Invitee",
        invitee_notes=None,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    await session.flush()
    return booking


async def test_find_by_slot_returns_booking(session):
    slot = await seed_slot(session)
    booking = await seed_booking(session, slot)

    repo = BookingRepository(session)
    found = await repo.find_by_slot(slot.id)

    assert found is not None
    assert found.slot_id == slot.id
    assert found.invitee_email == booking.invitee_email


async def test_find_by_slot_missing_returns_none(session):
    repo = BookingRepository(session)
    assert await repo.find_by_slot(uuid4()) is None


async def test_find_confirmed_by_slot_returns_confirmed(session):
    slot = await seed_slot(session)
    await seed_booking(session, slot)

    repo = BookingRepository(session)
    found = await repo.find_confirmed_by_slot(slot.id)

    assert found is not None
    assert found.status == BookingStatus.CONFIRMED


async def test_find_confirmed_by_slot_excludes_cancelled(session):
    slot = await seed_slot(session)
    booking = await seed_booking(session, slot)
    booking.status = BookingStatus.CANCELLED
    await session.flush()

    repo = BookingRepository(session)
    assert await repo.find_confirmed_by_slot(slot.id) is None


async def test_find_by_host_filters_by_host(session):
    slot = await seed_slot(session)
    await seed_booking(session, slot)

    repo = BookingRepository(session)
    items = await repo.find_by_host(slot.host_id)

    assert len(items) == 1
    assert all(item.host_id == slot.host_id for item in items)


async def test_find_by_host_paginates_and_orders(session):
    host = await seed_host(session)
    event_type = await seed_event_type(session, host)

    for i in range(3):
        slot = Slot(
            host_id=host.id,
            event_type_id=event_type.id,
            start_at=None,
            end_at=None,
            status=SlotStatus.AVAILABLE,
        )
        slot_window(slot)
        slot.start_at = slot.start_at.replace(hour=9 + i)
        slot.end_at = slot.start_at.replace(minute=30)
        session.add(slot)
        await session.flush()
        await seed_booking(session, slot)

    repo = BookingRepository(session)
    page_one = await repo.find_by_host(host.id, offset=0, limit=2)
    assert len(page_one) == 2
    page_two = await repo.find_by_host(host.id, offset=2, limit=2)
    assert len(page_two) == 1


async def test_find_by_host_empty_page(session):
    repo = BookingRepository(session)
    assert await repo.find_by_host(uuid4(), offset=10, limit=10) == []


async def test_count_by_host(session):
    slot = await seed_slot(session)
    await seed_booking(session, slot)

    repo = BookingRepository(session)
    assert await repo.count_by_host(slot.host_id) == 1
    assert await repo.count_by_host(uuid4()) == 0


async def test_exists_confirmed_for_slot(session):
    slot = await seed_slot(session)
    await seed_booking(session, slot)

    repo = BookingRepository(session)
    assert await repo.exists_confirmed_for_slot(slot.id) is True
    assert await repo.exists_confirmed_for_slot(uuid4()) is False


async def test_find_slot_for_update_compiles_with_for_update():
    compiled = str(
        select(Slot)
        .where(Slot.id == uuid4())
        .with_for_update()
        .compile(dialect=pg_dialect())
    )
    assert "FOR UPDATE" in compiled.upper()


async def test_find_slot_for_update_returns_slot(session):
    slot = await seed_slot(session)
    repo = BookingRepository(session)

    found = await repo.find_slot_for_update(slot.id)
    assert found is not None
    assert found.id == slot.id


async def test_find_slot_for_update_missing_returns_none(session):
    repo = BookingRepository(session)
    assert await repo.find_slot_for_update(uuid4()) is None


async def test_optimistic_occupy_available_slot_succeeds(session):
    slot = await seed_slot(session)
    repo = BookingRepository(session)

    occupied = await repo.try_occupy_slot(slot.id)
    assert occupied is True

    await session.refresh(slot)
    assert slot.status == SlotStatus.BOOKED


async def test_optimistic_occupy_booked_slot_fails(session):
    slot = await seed_slot(session, status=SlotStatus.BOOKED)
    repo = BookingRepository(session)

    occupied = await repo.try_occupy_slot(slot.id)
    assert occupied is False

    await session.refresh(slot)
    assert slot.status == SlotStatus.BOOKED


async def test_database_rejects_second_confirmed_booking_same_slot(session):
    slot = await seed_slot(session)
    await seed_booking(session, slot)

    repo = BookingRepository(session)
    second = Booking(
        slot_id=slot.id,
        host_id=slot.host_id,
        event_type_id=slot.event_type_id,
        invitee_email="other@example.com",
        invitee_name="Other",
        invitee_notes=None,
        status=BookingStatus.CONFIRMED,
    )

    with pytest.raises(IntegrityError):
        await repo.save(second)
