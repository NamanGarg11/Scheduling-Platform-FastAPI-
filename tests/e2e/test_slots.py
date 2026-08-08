from datetime import datetime, time as dtime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def expected_utc_starts(
    generator_date,
    start: str,
    end: str,
    duration: int,
    before: int = 0,
    after: int = 0,
    timezone_name: str = "Asia/Kolkata",
) -> list[datetime]:
    zone = ZoneInfo(timezone_name)
    hour_start, minute_start = (int(part) for part in start.split(":"))
    hour_end, minute_end = (int(part) for part in end.split(":"))
    window_start = datetime.combine(
        generator_date,
        dtime(hour_start, minute_start),
        tzinfo=zone,
    )
    window_end = datetime.combine(
        generator_date,
        dtime(hour_end, minute_end),
        tzinfo=zone,
    )
    occupied = timedelta(minutes=duration + before + after)
    starts: list[datetime] = []
    cursor = window_start
    while cursor + occupied <= window_end:
        starts.append((cursor + timedelta(minutes=before)).astimezone(timezone.utc))
        cursor += occupied
    return starts


def slot_start_times(gen_body: dict) -> list[datetime]:
    return sorted(parse_utc(slot["start_at"]) for slot in gen_body["slots"])


async def test_generate_slots_full_flow(slots_env, db, window_dates, generate_slots):
    event_type_id = slots_env["event_type_id"]
    host_id = slots_env["host_id"]

    response = await generate_slots(
        event_type_id,
        window_dates.monday,
        window_dates.monday,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["generated_count"] == 4
    assert body["skipped_count"] == 0
    assert len(body["slots"]) == 4

    starts = slot_start_times(body)
    assert starts == expected_utc_starts(
        window_dates.monday, "09:00", "12:00", 30, before=5, after=10,
    )

    for slot in body["slots"]:
        assert slot["host_id"] == host_id
        assert slot["event_type_id"] == event_type_id
        assert slot["status"] == "AVAILABLE"
        assert parse_utc(slot["end_at"]) > parse_utc(slot["start_at"])

    rows = await db(
        "SELECT host_id, event_type_id, status FROM slots "
        "WHERE event_type_id = :eid",
        {"eid": event_type_id},
    )
    assert len(rows) == 4
    assert all(str(row[0]) == host_id for row in rows)
    assert all(str(row[1]) == event_type_id for row in rows)
    assert all(str(row[2]) == "AVAILABLE" for row in rows)


async def test_generate_slots_outcome_matches_engine_for_all_durations(
    create_user,
    slot_maker,
    window_dates,
):
    cases = [
        (15, 12),
        (30, 6),
        (45, 4),
        (60, 3),
        (120, 1),
    ]
    for duration, expected_count in cases:
        host = (
            await create_user(
                name="Duration Host",
                email=f"duration-{duration}@example.com",
            )
        ).json()["data"]
        event_type, generation = await slot_maker(
            host,
            duration_minutes=duration,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
            title=f"Duration {duration}",
        )
        assert generation.status_code == 201, generation.text
        body = generation.json()
        assert body["generated_count"] == expected_count, f"duration={duration}"
        starts = slot_start_times(body)
        expected = expected_utc_starts(
            window_dates.monday, "09:00", "12:00", duration, 0, 0,
        )
        assert starts == expected, f"duration={duration}"


async def test_generate_slots_extra_long_duration_is_empty(
    create_user,
    slot_maker,
):
    host = (
        await create_user(name="Long Host", email="long@example.com")
    ).json()["data"]
    event_type, generation = await slot_maker(
        host,
        duration_minutes=480,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
        title="Too Long",
    )
    assert generation.status_code == 201, generation.text
    body = generation.json()
    assert body["generated_count"] == 0
    assert body["slots"] == []


async def test_generate_slots_buffer_matrix(create_user, slot_maker, window_dates):
    cases = [(0, 0), (5, 0), (0, 10), (5, 10)]
    for before, after in cases:
        host = (
            await create_user(
                name="Buffer Host",
                email=f"buffer-{before}-{after}@example.com",
            )
        ).json()["data"]
        event_type, generation = await slot_maker(
            host,
            buffer_before_minutes=before,
            buffer_after_minutes=after,
            title=f"Buffers {before}-{after}",
        )
        assert generation.status_code == 201, generation.text
        body = generation.json()
        starts = slot_start_times(body)
        assert starts == expected_utc_starts(
            window_dates.monday, "09:00", "12:00", 30, before, after,
        ), f"buffers={before},{after}"


async def test_generate_slots_availability_boundaries(
    create_user,
    slot_maker,
    window_dates,
):
    cases = [
        ("09:00", "10:00", 60, 0, 0, 1),
        ("09:00", "09:30", 30, 0, 0, 1),
        ("09:00", "09:29", 30, 0, 0, 0),
        ("09:00", "17:00", 60, 0, 0, 8),
        ("09:00", "17:00", 480, 0, 0, 1),
        ("09:00", "10:00", 61, 0, 0, 0),
    ]
    for index, (start, end, duration, before, after, expected) in enumerate(cases):
        host = (
            await create_user(
                name="Boundary Host",
                email=f"boundary-{index}-{expected}-{duration}@example.com",
            )
        ).json()["data"]
        event_type, generation = await slot_maker(
            host,
            start=start,
            end=end,
            duration_minutes=duration,
            buffer_before_minutes=before,
            buffer_after_minutes=after,
            title=f"Boundary {start}-{end} d{duration}",
        )
        assert generation.status_code == 201, generation.text
        body = generation.json()
        assert body["generated_count"] == expected, (
            f"window {start}-{end} duration={duration}"
        )
        assert slot_start_times(body) == expected_utc_starts(
            window_dates.monday, start, end, duration, before, after,
        )


async def test_generate_slots_buffer_overflow_never_exceeds_window(
    host,
    slot_maker,
    window_dates,
):
    # Window 09:00-10:00, occupied = 5 + 30 + 5 = 40 minutes.
    # The engine must generate a single slot 09:05-09:35 and no second slot.
    event_type, generation = await slot_maker(
        host,
        start="09:00",
        end="10:00",
        duration_minutes=30,
        buffer_before_minutes=5,
        buffer_after_minutes=5,
        title="Buffer Overflow",
    )
    assert generation.status_code == 201, generation.text
    body = generation.json()
    assert body["generated_count"] == 1
    starts = slot_start_times(body)
    assert starts == expected_utc_starts(
        window_dates.monday, "09:00", "10:00", 30, 5, 5,
    )
    for slot in body["slots"]:
        end_utc = parse_utc(slot["end_at"])
        window_end_utc = datetime.combine(
            window_dates.monday,
            dtime(10, 0),
            tzinfo=ZoneInfo("Asia/Kolkata"),
        ).astimezone(timezone.utc)
        assert end_utc <= window_end_utc


async def test_generate_slots_day_of_week_mismatch_has_no_slots(
    host,
    slot_maker,
    generate_slots,
    window_dates,
):
    event_type, monday_generation = await slot_maker(
        host,
        day="MONDAY",
        start_date=window_dates.monday,
        end_date=window_dates.monday,
        title="Monday Only",
    )
    assert monday_generation.status_code == 201, monday_generation.text
    assert monday_generation.json()["generated_count"] == 6

    tuesday = await generate_slots(
        event_type["id"],
        window_dates.tuesday,
        window_dates.tuesday,
    )
    assert tuesday.status_code == 201, tuesday.text
    assert tuesday.json()["generated_count"] == 0
    assert tuesday.json()["slots"] == []


async def test_generate_slots_multi_day_range_only_counts_matching(
    host,
    slot_maker,
    window_dates,
):
    event_type, generation = await slot_maker(
        host,
        day="MONDAY",
        start_date=window_dates.monday,
        end_date=window_dates.tuesday,
        title="Two Day Range",
    )
    assert generation.status_code == 201, generation.text
    assert generation.json()["generated_count"] == 6


async def test_generate_slots_inactive_event_type_returns_empty(
    host,
    create_event_type,
    create_availability,
    generate_slots,
    client,
    db,
    window_dates,
):
    event_type = (
        await create_event_type(host["id"], title="Disabled", duration_minutes=30)
    ).json()
    await create_availability(host["id"], day_of_week="MONDAY")

    update = await client.patch(
        f"/event-types/{event_type['id']}", json={"is_active": False},
    )
    assert update.status_code == 200, update.text

    generation = await generate_slots(
        event_type["id"],
        window_dates.monday,
        window_dates.monday,
    )
    assert generation.status_code == 201, generation.text
    body = generation.json()
    assert body["generated_count"] == 0
    assert body["slots"] == []

    rows = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": event_type["id"]},
    )
    assert rows[0][0] == 0


async def test_generate_slots_missing_event_type_404(generate_slots, window_dates):
    response = await generate_slots(
        str(uuid4()),
        window_dates.monday,
        window_dates.monday,
    )
    assert response.status_code == 404


async def test_generate_slots_end_before_start_rejected(generate_slots, window_dates):
    response = await generate_slots(
        str(uuid4()),
        window_dates.tuesday,
        window_dates.monday,
    )
    assert response.status_code == 400


async def test_generate_slots_rejects_extra_fields(generate_slots, window_dates):
    response = await generate_slots(
        str(uuid4()),
        window_dates.monday,
        window_dates.monday,
        unexpected="field",
    )
    assert response.status_code == 400


async def test_generate_slots_idempotent_across_runs(
    slots_env,
    generate_slots,
    db,
    window_dates,
):
    event_type_id = slots_env["event_type_id"]
    first = await generate_slots(event_type_id, window_dates.monday, window_dates.monday)
    assert first.status_code == 201, first.text
    second = await generate_slots(event_type_id, window_dates.monday, window_dates.monday)
    assert second.status_code == 201, second.text
    third = await generate_slots(event_type_id, window_dates.monday, window_dates.monday)
    assert third.status_code == 201, third.text

    assert first.json()["generated_count"] == 4
    assert first.json()["skipped_count"] == 0
    assert second.json()["generated_count"] == 0
    assert second.json()["skipped_count"] == 4
    assert third.json()["generated_count"] == 0
    assert third.json()["skipped_count"] == 4

    rows = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": event_type_id},
    )
    assert rows[0][0] == 4


async def test_generate_slots_no_availability_returns_empty(
    host,
    create_event_type,
    generate_slots,
    window_dates,
):
    event_type = (
        await create_event_type(host["id"], title="No Availability", duration_minutes=30)
    ).json()
    response = await generate_slots(
        event_type["id"], window_dates.monday, window_dates.monday,
    )
    assert response.status_code == 201, response.text
    assert response.json()["generated_count"] == 0


async def test_generate_slots_keeps_event_types_isolated(
    host,
    create_event_type,
    create_availability,
    generate_slots,
    db,
    window_dates,
):
    first = (
        await create_event_type(host["id"], title="First", duration_minutes=30)
    ).json()
    second = (
        await create_event_type(host["id"], title="Second", duration_minutes=45)
    ).json()
    await create_availability(host["id"], day_of_week="MONDAY")

    run_first = await generate_slots(first["id"], window_dates.monday, window_dates.monday)
    run_second = await generate_slots(second["id"], window_dates.monday, window_dates.monday)
    assert run_first.status_code == 201, run_first.text
    assert run_second.status_code == 201, run_second.text

    assert run_first.json()["generated_count"] == 6
    assert run_second.json()["generated_count"] == 4
    assert all(slot["event_type_id"] == first["id"] for slot in run_first.json()["slots"])
    assert all(slot["event_type_id"] == second["id"] for slot in run_second.json()["slots"])

    first_rows = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": first["id"]},
    )
    second_rows = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": second["id"]},
    )
    assert first_rows[0][0] == 6
    assert second_rows[0][0] == 4


async def test_generate_slots_keeps_hosts_isolated(
    host,
    second_host,
    create_event_type,
    create_availability,
    generate_slots,
    db,
    window_dates,
):
    first = (
        await create_event_type(host["id"], title="Host A", duration_minutes=30)
    ).json()
    second = (
        await create_event_type(second_host["id"], title="Host B", duration_minutes=30)
    ).json()
    await create_availability(host["id"], day_of_week="MONDAY")
    await create_availability(second_host["id"], day_of_week="MONDAY")

    run_a = await generate_slots(first["id"], window_dates.monday, window_dates.monday)
    run_b = await generate_slots(second["id"], window_dates.monday, window_dates.monday)
    assert run_a.status_code == 201, run_a.text
    assert run_b.status_code == 201, run_b.text

    assert all(slot["host_id"] == host["id"] for slot in run_a.json()["slots"])
    assert all(slot["host_id"] == second_host["id"] for slot in run_b.json()["slots"])

    host_a_rows = await db(
        "SELECT count(*) FROM slots WHERE host_id = :hid",
        {"hid": host["id"]},
    )
    host_b_rows = await db(
        "SELECT count(*) FROM slots WHERE host_id = :hid",
        {"hid": second_host["id"]},
    )
    assert host_a_rows[0][0] == 6
    assert host_b_rows[0][0] == 6


async def test_generate_slots_respects_timezone(
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    utc_host = (
        await create_user(name="UTC Host", email="utc@example.com", timezone="UTC")
    ).json()["data"]
    event_type = (
        await create_event_type(utc_host["id"], title="UTC Event", duration_minutes=30)
    ).json()
    await create_availability(
        utc_host["id"],
        day_of_week="MONDAY",
        start_time="09:00",
        end_time="12:00",
    )

    response = await generate_slots(
        event_type["id"], window_dates.monday, window_dates.monday,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["generated_count"] == 6
    first_start = parse_utc(body["slots"][0]["start_at"])
    assert first_start.hour == 9