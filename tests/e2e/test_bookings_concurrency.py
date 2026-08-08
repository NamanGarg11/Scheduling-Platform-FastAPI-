import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.bookings.repository import BookingRepository
from app.bookings.schema import CreateBookingRequest
from app.bookings.service import BookingService
from app.slots.enums import SlotStatus
from app.users.repository import UserRepository


@pytest.fixture
async def session(clean_db):
    from app.config.database import SessionLocal

    async with SessionLocal() as s:
        yield s
        await s.rollback()


async def seed_race_state(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    host = (
        await create_user(name="Race Host", email=f"race-{uuid4().hex[:8]}@example.com")
    ).json()["data"]
    event_type = (
        await create_event_type(host["id"], title="Race", duration_minutes=30)
    ).json()
    await create_availability(host["id"], day_of_week="MONDAY")
    generation = await generate_slots(
        event_type["id"],
        window_dates.monday,
        window_dates.monday,
    )
    assert generation.status_code == 201, generation.text
    return {
        "host": host,
        "slot": generation.json()["slots"][0],
    }


def request_for(slot_id: str, email: str) -> dict:
    return {
        "slot_id": slot_id,
        "invitee_email": email,
        "invitee_name": "Invitee",
        "invitee_notes": None,
    }


async def test_concurrent_booking_exactly_one_succeeds(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    state = await seed_race_state(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    slot = state["slot"]

    async def book(email: str) -> int:
        response = await client.post(
            "/bookings",
            json=request_for(slot["id"], email),
        )
        return response.status_code

    statuses = await asyncio.gather(
        book("race-a@example.com"),
        book("race-b@example.com"),
    )

    assert sorted(statuses) == [201, 400]

    booking_rows = await db(
        "SELECT count(*) FROM bookings WHERE slot_id = :sid",
        {"sid": slot["id"]},
    )
    assert booking_rows[0][0] == 1

    confirmed_rows = await db(
        "SELECT count(*) FROM bookings WHERE slot_id = :sid AND status = 'confirmed'",
        {"sid": slot["id"]},
    )
    assert confirmed_rows[0][0] == 1

    slot_rows = await db(
        "SELECT status FROM slots WHERE id = :sid",
        {"sid": slot["id"]},
    )
    assert slot_rows[0][0] == "BOOKED"


async def test_concurrent_duplicate_by_same_invitee(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    state = await seed_race_state(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    slot = state["slot"]

    async def book() -> int:
        response = await client.post(
            "/bookings",
            json=request_for(slot["id"], "dup-a@example.com"),
        )
        return response.status_code

    statuses = await asyncio.gather(book(), book())
    assert sorted(statuses) == [201, 400]

    rows = await db(
        "SELECT count(*) FROM bookings WHERE slot_id = :sid",
        {"sid": slot["id"]},
    )
    assert rows[0][0] == 1


async def test_slot_remains_available_after_rollback(
    client,
    db,
    session,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    state = await seed_race_state(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    slot = state["slot"]

    repo = BookingRepository(session)
    user_repo = UserRepository(session)
    service = BookingService(repository=repo, user_repository=user_repo)

    request = CreateBookingRequest(
        slot_id=slot["id"],
        invitee_email="rollback-a@example.com",
        invitee_name="Rollback Invitee",
        invitee_notes=None,
    )
    result = await service.create_booking(request)
    assert result is not None

    await session.rollback()

    slot_state = await session.execute(
        text("SELECT status FROM slots WHERE id = :id"),
        {"id": slot["id"]},
    )
    assert slot_state.scalar() == SlotStatus.AVAILABLE.value

    booking_count = await session.scalar(
        text("SELECT count(*) FROM bookings WHERE slot_id = :id"),
        {"id": slot["id"]},
    )
    assert booking_count == 0
