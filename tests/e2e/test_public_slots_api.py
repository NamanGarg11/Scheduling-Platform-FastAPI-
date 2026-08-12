"""API + integration tests for the public slot listing (S3) on real Postgres."""

from datetime import date, datetime, timedelta, timezone


def _parse_utc(value: str) -> datetime:
    """Parse a serialized UTC timestamp (accepts 'Z' or '+00:00')."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc,
    )


async def _regenerate(client, host_id: str, **overrides) -> object:
    payload: dict = {}
    payload.update(overrides)
    return await client.post(
        "/api/v1/slots/regenerate",
        json=payload,
        headers={"x-user-id": str(host_id)},
    )


async def _public_get(client, host_id: str, slug: str, **params) -> object:
    return await client.get(
        f"/api/public/users/{host_id}/event-types/{slug}/slots",
        params=params or None,
    )


async def test_public_listing_returns_available_slots_grouped_locally(
    client,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    event_type = (
        await create_event_type(host["id"], title="Consult", duration_minutes=30)
    ).json()
    await create_availability(host["id"], day_of_week="MONDAY")

    monday = window_dates.monday.isoformat()
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    response = await _public_get(
        client,
        host["id"],
        event_type["slug"],
        from_date=monday,
        to_date=monday,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["event_type"]["id"] == event_type["id"]
    assert body["event_type"]["slug"] == event_type["slug"]
    assert body["event_type"]["title"] == "Consult"
    assert body["timezone"] == "Asia/Kolkata"

    assert [day["date"] for day in body["days"]] == [monday]
    slots = body["days"][0]["slots"]
    assert len(slots) == 6

    # 09:00 IST = 03:30 UTC (host timezone is Asia/Kolkata).
    starts = [_parse_utc(slot["start_at"]) for slot in slots]
    expected_first = datetime.fromisoformat(f"{monday}T03:30:00Z").astimezone(
        timezone.utc,
    )
    assert starts[0] == expected_first
    assert starts == sorted(starts)  # ordered by start_at
    # Timestamps are UTC instants, never the local wall clock.
    assert all(dt.tzinfo == timezone.utc for dt in starts)


async def test_public_listing_empty_when_no_slots(client, host, create_event_type):
    event_type = (
        await create_event_type(host["id"], title="Empty", duration_minutes=30)
    ).json()

    monday = date.today() + timedelta(days=(0 - date.today().weekday()) % 7 + 7)
    response = await _public_get(
        client,
        host["id"],
        event_type["slug"],
        from_date=monday.isoformat(),
        to_date=monday.isoformat(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["days"] == []


async def test_unknown_user_raises_404(client, host):
    response = await _public_get(
        client,
        "00000000-0000-0000-0000-000000000000",
        "consultation",
    )
    assert response.status_code == 404, response.text


async def test_unknown_event_type_raises_404(client, host):
    response = await _public_get(
        client,
        host["id"],
        "does-not-exist",
    )
    assert response.status_code == 404, response.text


async def test_event_type_of_another_user_raises_404(
    client,
    host,
    second_host,
    create_event_type,
):
    # The event type belongs to host, not second_host. Requesting it under
    # second_host must 404 (no existence leak).
    event_type = (
        await create_event_type(host["id"], title="Mine", duration_minutes=30)
    ).json()

    response = await _public_get(
        client,
        second_host["id"],
        event_type["slug"],
    )
    assert response.status_code == 404, response.text


async def test_inactive_event_type_raises_404(
    client,
    host,
    create_event_type,
):
    event_type = (
        await create_event_type(host["id"], title="Hidden", duration_minutes=30)
    ).json()
    await client.patch(
        f"/event-types/{event_type['id']}",
        json={"is_active": False},
    )

    response = await _public_get(
        client,
        host["id"],
        event_type["slug"],
    )
    assert response.status_code == 404, response.text


async def test_invalid_range_raises_400(client, host, create_event_type):
    event_type = (
        await create_event_type(host["id"], title="Range", duration_minutes=30)
    ).json()
    response = await _public_get(
        client,
        host["id"],
        event_type["slug"],
        from_date="2026-08-11",
        to_date="2026-08-10",
    )
    assert response.status_code == 400, response.text


async def test_range_over_62_days_raises_400(client, host, create_event_type):
    event_type = (
        await create_event_type(host["id"], title="Range", duration_minutes=30)
    ).json()
    response = await _public_get(
        client,
        host["id"],
        event_type["slug"],
        from_date="2026-08-01",
        to_date="2026-10-15",
    )
    assert response.status_code == 400, response.text


async def test_invalid_timezone_raises_400(client, host, create_event_type):
    event_type = (
        await create_event_type(host["id"], title="Timezone", duration_minutes=30)
    ).json()
    response = await _public_get(
        client,
        host["id"],
        event_type["slug"],
        timezone="Mars/Olympus",
    )
    assert response.status_code == 400, response.text


async def test_booked_and_blocked_slots_are_omitted(
    client,
    db,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    event_type = (
        await create_event_type(host["id"], title="Filter", duration_minutes=30)
    ).json()
    availability = (
        await create_availability(host["id"], day_of_week="MONDAY")
    ).json()

    monday = window_dates.monday.isoformat()
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    # Book the 10:00 IST slot (04:30 UTC).
    rows = await db(
        "SELECT id FROM slots WHERE event_type_id = :et AND start_at = :s",
        {"et": event_type["id"], "s": _dt(f"{monday}T04:30:00Z")},
    )
    booking = await client.post(
        "/bookings",
        json={
            "slot_id": str(rows[0][0]),
            "invitee_email": "public-omit@example.com",
            "invitee_name": "Invitee",
            "invitee_notes": None,
        },
    )
    assert booking.status_code == 201, booking.text

    # Shrink availability -> regeneration blocks the obsolete slots.
    await client.patch(
        f"/availability/{availability['id']}",
        json={"start_time": "11:00", "end_time": "12:00"},
    )
    await _regenerate(client, host["id"], from_date=monday, to_date=monday)

    response = await _public_get(
        client,
        host["id"],
        event_type["slug"],
        from_date=monday,
        to_date=monday,
    )
    assert response.status_code == 200, response.text
    slots = response.json()["days"][0]["slots"]
    starts = [_parse_utc(slot["start_at"]) for slot in slots]

    # Only 11:00 and 11:30 IST survive as AVAILABLE (05:30Z, 06:00Z).
    assert starts == [
        _dt(f"{monday}T05:30:00Z"),
        _dt(f"{monday}T06:00:00Z"),
    ]


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
        timezone.utc,
    )


async def test_cross_day_grouping_uses_local_date_not_utc(
    client,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    """02:00 IST Monday = 20:30 UTC Sunday.

    Grouping must follow the requested timezone: Monday for Asia/Kolkata,
    Sunday for UTC — while the timestamps stay the same UTC instants.
    """
    event_type = (
        await create_event_type(host["id"], title="Late", duration_minutes=30)
    ).json()
    await create_availability(
        host["id"],
        day_of_week="MONDAY",
        start_time="02:00",
        end_time="03:00",
    )

    monday = window_dates.monday
    sunday = monday - timedelta(days=1)
    await _regenerate(
        client,
        host["id"],
        from_date=monday.isoformat(),
        to_date=monday.isoformat(),
    )

    # Both views use a range that includes the Sunday-20:30Z slots.
    kolkata = await _public_get(
        client,
        host["id"],
        event_type["slug"],
        from_date=sunday.isoformat(),
        to_date=monday.isoformat(),
    )
    assert kolkata.status_code == 200, kolkata.text
    kolkata_body = kolkata.json()
    assert kolkata_body["timezone"] == "Asia/Kolkata"
    assert [day["date"] for day in kolkata_body["days"]] == [monday.isoformat()]

    utc_view = await _public_get(
        client,
        host["id"],
        event_type["slug"],
        from_date=sunday.isoformat(),
        to_date=monday.isoformat(),
        timezone="UTC",
    )
    assert utc_view.status_code == 200, utc_view.text
    utc_body = utc_view.json()
    assert utc_body["timezone"] == "UTC"
    assert [day["date"] for day in utc_body["days"]] == [sunday.isoformat()]

    # Same UTC instants in both views.
    kolkata_starts = [
        _parse_utc(slot["start_at"])
        for day in kolkata_body["days"]
        for slot in day["slots"]
    ]
    utc_starts = [
        _parse_utc(slot["start_at"])
        for day in utc_body["days"]
        for slot in day["slots"]
    ]
    assert kolkata_starts == utc_starts
    assert kolkata_starts[0] == _dt(f"{sunday.isoformat()}T20:30:00Z")


async def test_query_uses_existing_index(
    client,
    db,
    host,
    create_event_type,
    create_availability,
    window_dates,
):
    """Seed a realistic inventory and verify the public query plan uses the
    existing unique index (event_type_id, start_at, end_at) — no new index."""

    event_type = (
        await create_event_type(host["id"], title="Indexed", duration_minutes=30)
    ).json()
    await create_availability(host["id"], day_of_week="MONDAY")

    monday = window_dates.monday
    # Seed ~62 days of inventory (~372 slots) so the planner has realistic stats.
    await _regenerate(
        client,
        host["id"],
        from_date=monday.isoformat(),
        to_date=(monday + timedelta(days=61)).isoformat(),
    )

    # A narrow one-day window from the large table: the planner should use the
    # existing unique index (event_type_id, start_at, end_at).
    tuesday = monday + timedelta(days=1)
    explain = await db(
        "EXPLAIN (FORMAT JSON) "
        "SELECT id FROM slots "
        "WHERE event_type_id = '" + event_type["id"] + "'::uuid "
        "AND start_at >= '" + monday.isoformat() + "T00:00:00Z' "
        "AND start_at < '" + tuesday.isoformat() + "T00:00:00Z' "
        "AND status = 'AVAILABLE' "
        "ORDER BY start_at",
    )
    plan = str(explain)
    assert "uq_slot_event_type_start_end" in plan or "Index Scan" in plan, plan
