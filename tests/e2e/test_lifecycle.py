from uuid import uuid4


async def test_full_lifecycle_scheduling_flow(
    host,
    create_event_type,
    create_availability,
    generate_slots,
    client,
    db,
    window_dates,
):
    event_type = (
        await create_event_type(host["id"], title="Lifecycle", duration_minutes=30)
    ).json()
    availability = (
        await create_availability(host["id"], day_of_week="MONDAY", start_time="09:00", end_time="12:00")
    ).json()

    first = await generate_slots(event_type["id"], window_dates.monday, window_dates.monday)
    assert first.status_code == 201, first.text
    assert first.json()["generated_count"] == 6

    update_event = client.patch(f"/event-types/{event_type['id']}", json={"title": "Lifecycle V2"})
    updated = await update_event
    assert updated.status_code == 200, updated.text
    assert updated.json()["slug"] == "lifecycle-v2"

    update_availability = await client.patch(
        f"/availability/{availability['id']}",
        json={"start_time": "10:00", "end_time": "13:00"},
    )
    assert update_availability.status_code == 200, update_availability.text

    second = await generate_slots(event_type["id"], window_dates.monday, window_dates.monday)
    assert second.status_code == 201, second.text
    assert second.json()["generated_count"] == 2
    rows = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": event_type["id"]},
    )
    assert rows[0][0] == 8

    delete_availability = await client.delete(f"/availability/{availability['id']}")
    assert delete_availability.status_code == 204

    third = await generate_slots(event_type["id"], window_dates.monday, window_dates.monday)
    assert third.status_code == 201, third.text
    assert third.json()["generated_count"] == 0

    delete_event = await client.delete(f"/event-types/{event_type['id']}")
    assert delete_event.status_code == 204

    after_delete = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": event_type["id"]},
    )
    assert after_delete[0][0] == 0


async def test_delete_event_type_cascades_to_slots(
    host,
    create_event_type,
    create_availability,
    generate_slots,
    client,
    db,
    window_dates,
):
    event = (await create_event_type(host["id"], title="Cascade", duration_minutes=30)).json()
    await create_availability(host["id"], day_of_week="MONDAY")
    await generate_slots(event["id"], window_dates.monday, window_dates.monday)

    before = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": event["id"]},
    )
    assert before[0][0] == 6

    delete = await client.delete(f"/event-types/{event['id']}")
    assert delete.status_code == 204

    after = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": event["id"]},
    )
    assert after[0][0] == 0


async def test_delete_host_cascades_to_children(
    host,
    create_event_type,
    create_availability,
    generate_slots,
    client,
    db,
    window_dates,
):
    event = (await create_event_type(host["id"], title="Cascade Host", duration_minutes=30)).json()
    await create_availability(host["id"], day_of_week="MONDAY")
    await generate_slots(event["id"], window_dates.monday, window_dates.monday)

    delete = await client.delete(f"/users/{host['id']}")
    assert delete.status_code == 200, delete.text

    event_rows = await db(
        "SELECT count(*) FROM event_types WHERE host_id = :hid",
        {"hid": host["id"]},
    )
    availability_rows = await db(
        "SELECT count(*) FROM availability WHERE host_id = :hid",
        {"hid": host["id"]},
    )
    slot_rows = await db(
        "SELECT count(*) FROM slots WHERE host_id = :hid",
        {"hid": host["id"]},
    )
    assert event_rows[0][0] == 0
    assert availability_rows[0][0] == 0
    assert slot_rows[0][0] == 0


async def test_failed_operation_leaves_no_partial_state(create_event_type, db):
    prior = await db("SELECT count(*) FROM event_types")
    response = await create_event_type(
        str(uuid4()),
        title="Should Not Persist",
        duration_minutes=30,
    )
    assert response.status_code == 404

    after = await db("SELECT count(*) FROM event_types")
    assert after[0][0] == prior[0][0]