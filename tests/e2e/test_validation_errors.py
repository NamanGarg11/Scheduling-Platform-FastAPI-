from uuid import uuid4


REQUIRED_USER_FIELDS = ("success", "message", "details")


def assert_error_contract(body: dict, status_code: int, message: str | None = None) -> None:
    assert body["success"] is False
    assert isinstance(body["message"], str)
    if message is not None:
        assert body["message"] == message
    assert REQUIRED_USER_FIELDS == tuple(body.keys())
    assert "Traceback" not in body["message"]
    assert "Traceback" not in str(body)


async def test_validation_error_uses_standardized_contract(create_user):
    response = await create_user(name="A", email="not-an-email")
    assert response.status_code == 400
    body = response.json()
    assert_error_contract(body, 400, "Validation Failed")
    assert isinstance(body["details"], list)
    assert len(body["details"]) >= 1


async def test_not_found_uses_standardized_contract(client):
    response = await client.get(f"/users/{uuid4()}")
    assert response.status_code == 404
    assert_error_contract(response.json(), 404, "User not found.")


async def test_conflict_uses_standardized_contract(create_user):
    first = await create_user(email="dup@example.com", name="One")
    assert first.status_code == 201
    second = await create_user(email="dup@example.com", name="Two")
    assert second.status_code == 409
    assert_error_contract(second.json(), 409, "Email already exists.")


async def test_business_validation_uses_standardized_contract(
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
    assert_error_contract(response.json(), 400, "Location is required for in-person meetings.")


async def test_missing_host_header_returns_400(client):
    payload = {
        "title": "Headerless",
        "duration_minutes": 30,
        "location_type": "zoom",
        "location_value": None,
        "buffer_before_minutes": 0,
        "buffer_after_minutes": 0,
    }
    response = await client.post("/event-types", json=payload)
    assert response.status_code == 400
    assert_error_contract(response.json(), 400)


async def test_invalid_date_in_slot_request_returns_400(client):
    payload = {
        "event_type_id": str(uuid4()),
        "start_date": "not-a-date",
        "end_date": "not-a-date",
    }
    response = await client.post("/api/v1/slots/generate", json=payload)
    assert response.status_code == 400
    assert_error_contract(response.json(), 400)
    assert response.json()["details"]


async def test_wrong_field_types_return_400(create_user):
    response = await create_user(
        name=123,
        email="x@example.com",
    )
    assert response.status_code == 400
    assert_error_contract(response.json(), 400)


async def test_nonexistent_host_returns_safe_404_without_leaks(
    create_event_type,
):
    response = await create_event_type(
        str(uuid4()),
        title="Orphan Event",
        duration_minutes=30,
    )
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "Event type host not found."
    text = response.text
    assert "Traceback" not in text
    assert "asyncpg" not in text
    assert "postgres" not in text
    assert "password" not in text


async def test_create_event_type_invalid_location_400(create_event_type):
    response = await create_event_type(
        str(uuid4()),
        title="Bad Location",
        location_type="skywriting",
    )
    assert response.status_code == 400


async def test_repeated_delete_is_404(client, create_user):
    user = (await create_user(email="gone@example.com", name="Gone")).json()["data"]
    first = await client.delete(f"/users/{user['id']}")
    assert first.status_code == 200
    second = await client.delete(f"/users/{user['id']}")
    assert second.status_code == 404