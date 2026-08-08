from uuid import uuid4


async def test_create_availability_returns_201(
    host,
    create_availability,
    db,
):
    response = await create_availability(
        host["id"],
        day_of_week="MONDAY",
        start_time="09:00",
        end_time="12:00",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["host_id"] == host["id"]
    assert body["day_of_week"] == "MONDAY"
    assert body["start_time"] == "09:00:00"
    assert body["end_time"] == "12:00:00"
    assert body["is_available"] is True

    rows = await db(
        "SELECT host_id, day_of_week FROM availability WHERE id = :id",
        {"id": body["id"]},
    )
    assert len(rows) == 1
    assert str(rows[0][1]) == "MONDAY"


async def test_create_availability_defaults_to_available(host, create_availability):
    response = await create_availability(
        host["id"],
        day_of_week="TUESDAY",
        start_time="10:00",
        end_time="11:00",
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_available"] is True


async def test_create_availability_duplicate_day_conflict(
    host,
    create_availability,
):
    first = await create_availability(host["id"], day_of_week="MONDAY")
    assert first.status_code == 201, first.text

    second = await create_availability(host["id"], day_of_week="MONDAY")
    assert second.status_code == 409
    assert second.json()["success"] is False
    assert second.json()["message"] == "Availability already exists for MONDAY."


async def test_create_availability_same_day_different_hosts_allowed(
    host,
    second_host,
    create_availability,
):
    first = await create_availability(host["id"], day_of_week="MONDAY")
    second = await create_availability(second_host["id"], day_of_week="MONDAY")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text


async def test_create_availability_end_before_start_rejected(host, create_availability):
    response = await create_availability(
        host["id"],
        day_of_week="MONDAY",
        start_time="12:00",
        end_time="09:00",
    )
    assert response.status_code == 400


async def test_create_availability_start_equals_end_rejected_when_available(
    host,
    create_availability,
):
    response = await create_availability(
        host["id"],
        day_of_week="MONDAY",
        start_time="09:00",
        end_time="09:00",
        is_available=True,
    )
    assert response.status_code == 400


async def test_create_availability_identical_times_allowed_when_unavailable(
    host,
    create_availability,
):
    response = await create_availability(
        host["id"],
        day_of_week="MONDAY",
        start_time="09:00",
        end_time="09:00",
        is_available=False,
    )
    assert response.status_code == 201, response.text


async def test_create_availability_invalid_bad_time_format_rejected(host, create_availability):
    response = await create_availability(
        host["id"],
        day_of_week="MONDAY",
        start_time="25:00",
        end_time="12:00",
    )
    assert response.status_code == 400


async def test_create_availability_nonexistent_host_controlled_error(create_availability):
    response = await create_availability(
        str(uuid4()),
        day_of_week="MONDAY",
    )
    assert response.status_code != 500
    assert response.status_code == 404 or response.status_code == 409


async def test_create_availability_invalid_day_rejected(host, create_availability):
    response = await create_availability(
        host["id"],
        day_of_week="FUNDAY",
    )
    assert response.status_code == 400


async def test_week_schedule_returns_ordered_by_day(
    host,
    create_availability,
    client,
):
    for day, start, end in [
        ("SUNDAY", "09:00", "10:00"),
        ("WEDNESDAY", "10:00", "11:00"),
        ("MONDAY", "11:00", "12:00"),
        ("TUESDAY", "12:00", "13:00"),
    ]:
        response = await create_availability(
            host["id"], day_of_week=day, start_time=start, end_time=end,
        )
        assert response.status_code == 201, response.text

    schedule = await client.get(
        "/availability",
        headers={"x-user-id": host["id"]},
    )
    assert schedule.status_code == 200
    days = [item["day_of_week"] for item in schedule.json()]
    assert days == ["MONDAY", "TUESDAY", "WEDNESDAY", "SUNDAY"]


async def test_week_schedule_scoped_to_host(
    host,
    second_host,
    create_availability,
    client,
):
    await create_availability(host["id"], day_of_week="MONDAY")
    await create_availability(second_host["id"], day_of_week="TUESDAY")

    schedule = await client.get("/availability", headers={"x-user-id": host["id"]})
    assert {item["day_of_week"] for item in schedule.json()} == {"MONDAY"}


async def test_get_availability_returns_created(
    host,
    create_availability,
    client,
):
    availability = (
        await create_availability(host["id"], day_of_week="MONDAY")
    ).json()
    response = await client.get(f"/availability/{availability['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == availability["id"]


async def test_get_availability_not_found(client):
    response = await client.get(f"/availability/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["message"] == "Availability not found."


async def test_get_availability_malformed_id_rejected(client):
    response = await client.get("/availability/not-a-uuid")
    assert response.status_code == 400


async def test_update_availability_times_and_availability(
    host,
    create_availability,
    client,
):
    item = (
        await create_availability(
            host["id"],
            day_of_week="MONDAY",
            start_time="09:00",
            end_time="12:00",
        )
    ).json()
    response = await client.patch(
        f"/availability/{item['id']}",
        json={"start_time": "10:00", "end_time": "13:00", "is_available": False},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["start_time"] == "10:00:00"
    assert body["end_time"] == "13:00:00"
    assert body["is_available"] is False


async def test_update_availability_invalid_range_rejected(
    host,
    create_availability,
    client,
):
    item = (
        await create_availability(
            host["id"], day_of_week="MONDAY", start_time="09:00", end_time="12:00",
        )
    ).json()
    response = await client.patch(
        f"/availability/{item['id']}",
        json={"start_time": "13:00", "end_time": "12:00"},
    )
    assert response.status_code == 400


async def test_update_availability_not_found(client):
    response = await client.patch(
        f"/availability/{uuid4()}",
        json={"start_time": "10:00"},
    )
    assert response.status_code == 404


async def test_delete_availability_200_then_not_found(
    host,
    create_availability,
    client,
    db,
):
    item = (await create_availability(host["id"], day_of_week="MONDAY")).json()
    response = await client.delete(f"/availability/{item['id']}")
    assert response.status_code == 204

    after = await client.get(f"/availability/{item['id']}")
    assert after.status_code == 404

    rows = await db(
        "SELECT id FROM availability WHERE id = :id",
        {"id": item["id"]},
    )
    assert rows == []


async def test_delete_availability_not_found(client):
    response = await client.delete(f"/availability/{uuid4()}")
    assert response.status_code == 404