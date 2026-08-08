import asyncio

from uuid import uuid4


async def test_concurrent_duplicate_availability_same_day(
    host,
    client,
    db,
):
    payload = {
        "day_of_week": "MONDAY",
        "start_time": "09:00",
        "end_time": "12:00",
        "is_available": True,
    }

    async def create() -> object:
        return await client.post(
            "/availability",
            json=payload,
            headers={"x-user-id": host["id"]},
        )

    responses = await asyncio.gather(create(), create())
    statuses = sorted(response.status_code for response in responses)
    assert 201 in statuses
    assert statuses.count(201) == 1

    rows = await db(
        "SELECT count(*) FROM availability WHERE host_id = :hid AND day_of_week = 'MONDAY'",
        {"hid": host["id"]},
    )
    assert rows[0][0] == 1

    for response in responses:
        assert "Traceback" not in response.text


async def test_concurrent_slot_generation_same_event_type(
    slots_env,
    client,
    db,
    window_dates,
):
    event_type_id = slots_env["event_type_id"]
    payload = {
        "event_type_id": event_type_id,
        "start_date": window_dates.monday.isoformat(),
        "end_date": window_dates.monday.isoformat(),
    }

    async def generate() -> object:
        return await client.post("/api/v1/slots/generate", json=payload)

    responses = await asyncio.gather(generate(), generate())
    statuses = [response.status_code for response in responses]
    assert 201 in statuses

    rows = await db(
        "SELECT count(*) FROM slots WHERE event_type_id = :eid",
        {"eid": event_type_id},
    )
    assert rows[0][0] == 4

    for response in responses:
        assert "Traceback" not in response.text