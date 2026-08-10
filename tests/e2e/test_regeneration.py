"""Integration tests for slot regeneration (S2-B) against real Postgres."""

import asyncio
from datetime import date, datetime
from uuid import uuid4


def _dt(iso: str) -> datetime:
    """ISO-8601 string with Z -> aware datetime (asyncpg needs real datetimes)."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _day_bounds(monday: str, tuesday: str) -> tuple[datetime, datetime]:
    return _dt(f"{monday}T00:00:00Z"), _dt(f"{tuesday}T00:00:00Z")


async def _regenerate(client, host_id: str, **overrides) -> object:
    payload: dict = {}
    payload.update(overrides)
    return await client.post(
        "/api/v1/slots/regenerate",
        json=payload,
        headers={"x-user-id": str(host_id)},
    )


async def _slot_rows(db, host_id: str, monday: str, tuesday: str) -> list[tuple]:
    start, end = _day_bounds(monday, tuesday)
    return await db(
        "SELECT id, start_at, status FROM slots WHERE host_id = :hid AND "
        "start_at >= :s AND start_at < :e ORDER BY start_at",
        {
            "hid": host_id,
            "s": start,
            "e": end,
        },
    )


async def test_regenerate_creates_slots_and_is_idempotent(
    client,
    db,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    await create_event_type(host["id"], title="Regen", duration_minutes=30)
    await create_availability(host["id"], day_of_week="MONDAY")

    monday = window_dates.monday.isoformat()
    tuesday = window_dates.tuesday.isoformat()
    response = await _regenerate(
        client,
        host["id"],
        from_date=monday,
        to_date=monday,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generated_count"] == 6
    assert body["kept_count"] == 0
    assert body["booked_count"] == 0

    count = len(await _slot_rows(db, host["id"], monday, tuesday))
    assert count == 6

    # Idempotent: running again must not duplicate anything.
    second = await _regenerate(
        client,
        host["id"],
        from_date=monday,
        to_date=monday,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["generated_count"] == 0
    assert second_body["kept_count"] == 6

    assert len(await _slot_rows(db, host["id"], monday, tuesday)) == 6


async def test_regenerate_obsolete_available_becomes_blocked(
    client,
    db,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    await create_event_type(host["id"], title="Regen", duration_minutes=30)
    availability = (
        await create_availability(host["id"], day_of_week="MONDAY")
    ).json()

    monday = window_dates.monday.isoformat()
    tuesday = window_dates.tuesday.isoformat()
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    # Shrink availability to 10:00-11:00 -> 09:00/09:30/11:00/11:30 go obsolete.
    await client.patch(
        f"/availability/{availability['id']}",
        json={"start_time": "10:00", "end_time": "11:00"},
    )

    response = await _regenerate(client, host["id"], from_date=monday, to_date=monday)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generated_count"] == 0
    assert body["kept_count"] == 2
    assert body["blocked_count"] == 4

    # Host is Asia/Kolkata (UTC+5:30): 09:00-12:00 IST is 03:30-06:30 UTC.
    statuses = {
        row[1]: row[2]
        for row in await _slot_rows(db, host["id"], monday, tuesday)
    }
    assert statuses[_dt(f"{monday}T03:30:00Z")] == "BLOCKED"  # 09:00 IST
    assert statuses[_dt(f"{monday}T04:00:00Z")] == "BLOCKED"  # 09:30 IST
    assert statuses[_dt(f"{monday}T04:30:00Z")] == "AVAILABLE"  # 10:00 IST
    assert statuses[_dt(f"{monday}T05:00:00Z")] == "AVAILABLE"  # 10:30 IST
    assert statuses[_dt(f"{monday}T05:30:00Z")] == "BLOCKED"  # 11:00 IST
    assert statuses[_dt(f"{monday}T06:00:00Z")] == "BLOCKED"  # 11:30 IST


async def test_regenerate_restores_stale_blocked(
    client,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    await create_event_type(host["id"], title="Regen", duration_minutes=30)
    availability = (
        await create_availability(host["id"], day_of_week="MONDAY")
    ).json()

    monday = window_dates.monday.isoformat()
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)
    await client.patch(
        f"/availability/{availability['id']}",
        json={"start_time": "10:00", "end_time": "11:00"},
    )
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    # Widen availability back -> the four BLOCKED slots become valid again.
    await client.patch(
        f"/availability/{availability['id']}",
        json={"start_time": "09:00", "end_time": "12:00"},
    )
    response = await _regenerate(client, host["id"], from_date=monday, to_date=monday)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["restored_count"] == 4
    assert body["kept_count"] == 2
    assert body["generated_count"] == 0


async def test_regenerate_never_touches_booked(
    client,
    db,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    await create_event_type(host["id"], title="Regen", duration_minutes=30)
    availability = (
        await create_availability(host["id"], day_of_week="MONDAY")
    ).json()

    monday = window_dates.monday.isoformat()
    tuesday = window_dates.tuesday.isoformat()
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    rows = await _slot_rows(db, host["id"], monday, tuesday)
    slot_by_start = {row[1]: row[0] for row in rows}
    booked_slot_id = slot_by_start[_dt(f"{monday}T04:30:00Z")]  # 10:00 IST

    booking = await client.post(
        "/bookings",
        json={
            "slot_id": str(booked_slot_id),
            "invitee_email": "regen-book@example.com",
            "invitee_name": "Invitee",
            "invitee_notes": None,
        },
    )
    assert booking.status_code == 201, booking.text

    # Make 10:00 no longer available, then regenerate: the booked slot must
    # remain BOOKED even though regeneration would otherwise block it.
    await client.patch(
        f"/availability/{availability['id']}",
        json={"start_time": "11:00", "end_time": "12:00"},
    )
    response = await _regenerate(client, host["id"], from_date=monday, to_date=monday)
    assert response.status_code == 200, response.text
    assert response.json()["booked_count"] == 1

    slot_state = await db(
        "SELECT status FROM slots WHERE id = :id",
        {"id": booked_slot_id},
    )
    assert slot_state[0][0] == "BOOKED"

    booking_count = await db(
        "SELECT count(*) FROM bookings WHERE slot_id = :id",
        {"id": booked_slot_id},
    )
    assert booking_count[0][0] == 1


async def test_regenerate_applies_exceptions(
    client,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    await create_event_type(host["id"], title="Regen", duration_minutes=30)
    await create_availability(host["id"], day_of_week="MONDAY")

    monday = window_dates.monday.isoformat()
    exception = await client.post(
        "/availability/exceptions",
        json={
            "kind": "BLOCK_PARTIAL",
            "date": monday,
            "start_time": "10:00",
            "end_time": "11:00",
        },
        headers={"x-user-id": str(host["id"])},
    )
    assert exception.status_code == 201, exception.text

    response = await _regenerate(client, host["id"], from_date=monday, to_date=monday)
    assert response.status_code == 200, response.text
    # 09:00, 09:30, 11:00, 11:30 survive the 10:00-11:00 block.
    assert response.json()["generated_count"] == 4


async def test_regenerate_default_range_is_30_days(
    client,
    host,
    create_event_type,
    create_availability,
):
    await create_event_type(host["id"], title="Regen", duration_minutes=30)
    await create_availability(host["id"], day_of_week="MONDAY")

    response = await _regenerate(client, host["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert (
        date.fromisoformat(body["to_date"]) - date.fromisoformat(body["from_date"])
    ).days == 29
    assert body["timezone"] == "Asia/Kolkata"
    assert body["generated_count"] > 0


async def test_regenerate_invalid_range_raises_400(client, host):
    response = await _regenerate(
        client,
        host["id"],
        from_date="2026-08-11",
        to_date="2026-08-10",
    )
    assert response.status_code == 400, response.text


async def test_regenerate_unknown_host_raises_404(client):
    response = await _regenerate(client, str(uuid4()))
    assert response.status_code == 404, response.text


async def test_regenerate_booked_slot_collision_across_event_types(
    client,
    db,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    event_type_a = (
        await create_event_type(host["id"], title="Type A", duration_minutes=30)
    ).json()
    await create_availability(host["id"], day_of_week="MONDAY")

    monday = window_dates.monday.isoformat()
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    # Book Type A's 09:00 slot.
    rows = await db(
        "SELECT id FROM slots WHERE event_type_id = :et ORDER BY start_at LIMIT 1",
        {"et": event_type_a["id"]},
    )
    booking = await client.post(
        "/bookings",
        json={
            "slot_id": str(rows[0][0]),
            "invitee_email": "collide@example.com",
            "invitee_name": "Invitee",
            "invitee_notes": None,
        },
    )
    assert booking.status_code == 201, booking.text

    # A second event type for the same host: regeneration must not create a
    # 09:00 slot for it (the booking's occupancy [09:00, 09:30) collides).
    event_type_b = (
        await create_event_type(host["id"], title="Type B", duration_minutes=30)
    ).json()
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    rows_b = await db(
        "SELECT start_at FROM slots WHERE event_type_id = :et ORDER BY start_at",
        {"et": event_type_b["id"]},
    )
    starts = [row[0] for row in rows_b]
    # Type B must not get a 09:00 IST (03:30 UTC) slot; the booking's
    # occupancy [09:00, 09:30) IST collides with it.
    assert _dt(f"{monday}T03:30:00Z") not in starts
    assert len(starts) == 5  # 09:30..11:30 IST


async def test_regeneration_vs_booking_race(
    client,
    db,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    """Regeneration and booking racing on the same slot.

    Regeneration wants to BLOCK the 10:00 slot (availability shrank); a booking
    is fired for it concurrently. The only safe outcomes are:
      - booking wins: slot stays BOOKED, exactly one booking row; or
      - regeneration wins: slot is BLOCKED, booking rejected (0 rows).
    The forbidden outcomes: the slot ending AVAILABLE, or a booking on a
    blocked slot.
    """
    await create_event_type(host["id"], title="Race", duration_minutes=30)
    availability = (
        await create_availability(host["id"], day_of_week="MONDAY")
    ).json()

    monday = window_dates.monday.isoformat()
    tuesday = window_dates.tuesday.isoformat()
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    rows = await _slot_rows(db, host["id"], monday, tuesday)
    slot_by_start = {row[1]: row[0] for row in rows}
    race_slot_id = slot_by_start[_dt(f"{monday}T04:30:00Z")]  # 10:00 IST

    # 10:00 is no longer available -> regeneration would block it.
    await client.patch(
        f"/availability/{availability['id']}",
        json={"start_time": "11:00", "end_time": "12:00"},
    )

    async def book() -> int:
        response = await client.post(
            "/bookings",
            json={
                "slot_id": str(race_slot_id),
                "invitee_email": "race-regen@example.com",
                "invitee_name": "Invitee",
                "invitee_notes": None,
            },
        )
        return response.status_code

    async def regenerate() -> int:
        response = await _regenerate(
            client,
            host["id"],
            from_date=monday,
            to_date=monday,
        )
        return response.status_code

    statuses = await asyncio.gather(book(), regenerate())
    assert 200 in statuses  # regeneration always succeeds

    slot_state = await db(
        "SELECT status FROM slots WHERE id = :id",
        {"id": race_slot_id},
    )
    final_status = slot_state[0][0]
    booking_count = (
        await db(
            "SELECT count(*) FROM bookings WHERE slot_id = :id",
            {"id": race_slot_id},
        )
    )[0][0]

    assert final_status != "AVAILABLE"
    if final_status == "BOOKED":
        assert booking_count == 1
    else:
        assert final_status == "BLOCKED"
        assert booking_count == 0
