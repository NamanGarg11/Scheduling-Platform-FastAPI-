from uuid import uuid4


async def test_create_event_type_returns_201_with_slug(
    host,
    create_event_type,
    db,
):
    response = await create_event_type(
        host["id"],
        title="Consultation",
        duration_minutes=30,
        buffer_before_minutes=5,
        buffer_after_minutes=10,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == "consultation"
    assert body["host_id"] == host["id"]
    assert body["duration_minutes"] == 30
    assert body["buffer_before_minutes"] == 5
    assert body["buffer_after_minutes"] == 10
    assert body["is_active"] is True
    assert body["location_type"] == "zoom"

    rows = await db(
        "SELECT title, slug, host_id FROM event_types WHERE id = :id",
        {"id": body["id"]},
    )
    assert len(rows) == 1
    assert rows[0][1] == "consultation"


async def test_create_event_type_defaults_active_and_zero_buffers(host, create_event_type):
    response = await create_event_type(
        host["id"],
        title="Default Meeting",
        duration_minutes=15,
        location_type="phone",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["is_active"] is True
    assert body["buffer_before_minutes"] == 0
    assert body["buffer_after_minutes"] == 0


async def test_create_event_type_slug_unique_per_host(
    host,
    create_event_type,
):
    first = await create_event_type(host["id"], title="Consultation")
    second = await create_event_type(host["id"], title="Consultation")
    third = await create_event_type(host["id"], title="Consultation")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert third.status_code == 201, third.text
    slugs = [
        first.json()["slug"],
        second.json()["slug"],
        third.json()["slug"],
    ]
    assert slugs == ["consultation", "consultation-2", "consultation-3"]


async def test_create_event_type_same_title_allowed_for_different_hosts(
    host,
    second_host,
    create_event_type,
):
    first = await create_event_type(host["id"], title="Consultation")
    second = await create_event_type(second_host["id"], title="Consultation")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["slug"] == "consultation"
    assert second.json()["slug"] == "consultation"


async def test_create_event_type_in_person_requires_location(
    host,
    create_event_type,
):
    response = await create_event_type(
        host["id"],
        title="Office",
        location_type="in_person",
        location_value=None,
    )
    assert response.status_code == 400
    assert response.json()["success"] is False


async def test_create_event_type_accepts_in_person_with_location(
    host,
    create_event_type,
):
    response = await create_event_type(
        host["id"],
        title="Office",
        location_type="in_person",
        location_value="Room 42",
    )
    assert response.status_code == 201, response.text
    assert response.json()["location_type"] == "in_person"
    assert response.json()["location_value"] == "Room 42"


async def test_create_event_type_blank_location_value_rejected(
    host,
    create_event_type,
):
    response = await create_event_type(
        host["id"],
        title="Office",
        location_type="in_person",
        location_value="   ",
    )
    assert response.status_code == 400


async def test_create_event_type_nonexistent_host_controlled_error(
    client,
    create_event_type,
):
    response = await create_event_type(
        str(uuid4()),
        title="Orphan",
        duration_minutes=30,
    )
    assert response.status_code != 500
    assert response.status_code == 404 or response.status_code == 409


async def test_create_event_type_rejects_invalid_location_type(host, create_event_type):
    response = await create_event_type(
        host["id"],
        title="Bad Location",
        location_type="skywriting",
    )
    assert response.status_code == 400


async def test_create_event_type_rejects_zero_duration(host, create_event_type):
    response = await create_event_type(host["id"], title="Zero", duration_minutes=0)
    assert response.status_code == 400


async def test_create_event_type_rejects_negative_duration(host, create_event_type):
    response = await create_event_type(host["id"], title="Negative", duration_minutes=-5)
    assert response.status_code == 400


async def test_create_event_type_accepts_max_duration(host, create_event_type):
    response = await create_event_type(host["id"], title="Max", duration_minutes=480)
    assert response.status_code == 201, response.text


async def test_create_event_type_rejects_duration_over_max(host, create_event_type):
    response = await create_event_type(host["id"], title="Over", duration_minutes=481)
    assert response.status_code == 400


async def test_create_event_type_rejects_negative_buffer(host, create_event_type):
    response = await create_event_type(
        host["id"], title="Buffer", buffer_before_minutes=-1,
    )
    assert response.status_code == 400


async def test_create_event_type_rejects_buffer_over_max(host, create_event_type):
    response = await create_event_type(
        host["id"], title="Buffer", buffer_after_minutes=121,
    )
    assert response.status_code == 400


async def test_create_event_type_rejects_title_too_short(host, create_event_type):
    response = await create_event_type(host["id"], title="AB")
    assert response.status_code == 400


async def test_create_event_type_rejects_blank_title(host, create_event_type):
    response = await create_event_type(host["id"], title="   ")
    assert response.status_code == 400


async def test_create_event_type_rejects_missing_title(host, create_event_type):
    response = await create_event_type(host["id"], title=None)
    assert response.status_code == 400


async def test_create_event_type_requires_host_header(client, create_event_type):
    payload = {
        "title": "No Header",
        "duration_minutes": 30,
        "location_type": "zoom",
        "location_value": None,
        "buffer_before_minutes": 0,
        "buffer_after_minutes": 0,
    }
    response = await client.post("/event-types", json=payload)
    assert response.status_code == 400


async def test_get_event_type_returns_created(
    host,
    create_event_type,
    client,
):
    et = (await create_event_type(host["id"], title="Fetchable")).json()
    response = await client.get(f"/event-types/{et['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == et["id"]


async def test_get_event_type_not_found(client):
    response = await client.get(f"/event-types/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["message"] == "Event type not found."


async def test_get_event_type_malformed_id_rejected(client):
    response = await client.get("/event-types/not-a-uuid")
    assert response.status_code == 400


async def test_list_event_types_scoped_to_host(
    host,
    second_host,
    create_event_type,
    client,
):
    await create_event_type(host["id"], title="One")
    await create_event_type(host["id"], title="Two")
    await create_event_type(second_host["id"], title="Other")

    host_list = await client.get("/event-types", headers={"x-user-id": host["id"]})
    assert host_list.status_code == 200
    assert {item["title"] for item in host_list.json()} == {"One", "Two"}

    other_host_list = await client.get(
        "/event-types", headers={"x-user-id": second_host["id"]},
    )
    assert {item["title"] for item in other_host_list.json()} == {"Other"}


async def test_update_event_type_regenerates_slug(
    host,
    create_event_type,
    client,
):
    event_type = (await create_event_type(host["id"], title="Original Name")).json()
    response = await client.patch(
        f"/event-types/{event_type['id']}",
        json={"title": "Renamed"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Renamed"
    assert response.json()["slug"] == "renamed"


async def test_update_event_title_handles_collision(
    host,
    create_event_type,
    client,
):
    first = (await create_event_type(host["id"], title="Consultation")).json()
    second = (await create_event_type(host["id"], title="Second")).json()
    response = await client.patch(
        f"/event-types/{second['id']}",
        json={"title": "Consultation"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["slug"] == "consultation-2"


async def test_update_event_type_duration_and_buffers(
    host,
    create_event_type,
    client,
):
    event_type = (await create_event_type(host["id"], title="Mutable")).json()
    response = await client.patch(
        f"/event-types/{event_type['id']}",
        json={
            "duration_minutes": 60,
            "buffer_before_minutes": 5,
            "buffer_after_minutes": 15,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duration_minutes"] == 60
    assert body["buffer_before_minutes"] == 5
    assert body["buffer_after_minutes"] == 15


async def test_update_event_type_rejects_invalid_duration(
    host,
    create_event_type,
    client,
):
    event_type = (await create_event_type(host["id"], title="Strict")).json()
    response = await client.patch(
        f"/event-types/{event_type['id']}",
        json={"duration_minutes": 0},
    )
    assert response.status_code == 400


async def test_update_event_type_in_person_requires_location(
    host,
    create_event_type,
    client,
):
    event_type = (await create_event_type(host["id"], title="Office", location_type="zoom")).json()
    response = await client.patch(
        f"/event-types/{event_type['id']}",
        json={"location_type": "in_person", "location_value": None},
    )
    assert response.status_code == 400


async def test_update_event_type_not_found(client):
    response = await client.patch(f"/event-types/{uuid4()}", json={"title": "Missing"})
    assert response.status_code == 404


async def test_delete_event_type_returns_204_then_not_found(
    host,
    create_event_type,
    client,
    db,
):
    event_type = (await create_event_type(host["id"], title="Temp")).json()
    response = await client.delete(f"/event-types/{event_type['id']}")
    assert response.status_code == 204

    after = await client.get(f"/event-types/{event_type['id']}")
    assert after.status_code == 404

    rows = await db(
        "SELECT id FROM event_types WHERE id = :id",
        {"id": event_type["id"]},
    )
    assert rows == []


async def test_delete_event_type_not_found(client):
    response = await client.delete(f"/event-types/{uuid4()}")
    assert response.status_code == 404