from uuid import uuid4


async def test_create_user_returns_201_and_persists(create_user, db):
    response = await create_user(name="Host One", email="host@example.com")
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["name"] == "Host One"
    assert body["email"] == "host@example.com"
    assert body["slug"] == "host-one"
    assert body["timezone"] == "Asia/Kolkata"
    assert body["id"]

    rows = await db(
        "SELECT name, email, slug, timezone FROM users WHERE id = :uid",
        {"uid": body["id"]},
    )
    assert len(rows) == 1
    assert rows[0][0] == "Host One"
    assert rows[0][1] == "host@example.com"


async def test_create_user_uses_default_timezone_utc(create_user):
    response = await create_user(name="Neo", email="neo@example.com", timezone="UTC")
    assert response.status_code == 201, response.text
    assert response.json()["data"]["timezone"] == "UTC"


async def test_create_user_duplicate_email_conflict(create_user):
    first = await create_user(name="First", email="same@example.com")
    assert first.status_code == 201, first.text
    second = await create_user(name="Second", email="same@example.com")
    assert second.status_code == 409
    assert second.json()["success"] is False
    assert second.json()["message"] == "Email already exists."


async def test_create_user_generates_unique_slugs(create_user):
    first = await create_user(name="Alice Smith", email="a@example.com")
    second = await create_user(name="Alice Smith", email="b@example.com")
    third = await create_user(name="Alice Smith", email="c@example.com")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert third.status_code == 201, third.text
    slugs = [
        first.json()["data"]["slug"],
        second.json()["data"]["slug"],
        third.json()["data"]["slug"],
    ]
    assert slugs == ["alice-smith", "alice-smith-2", "alice-smith-3"]


async def test_create_user_rejects_missing_name(create_user):
    response = await create_user(email="x@example.com", name=None)
    assert response.status_code == 400
    assert response.json()["success"] is False


async def test_create_user_rejects_short_name(create_user):
    response = await create_user(name="A", email="x@example.com")
    assert response.status_code == 400


async def test_create_user_rejects_blank_name(create_user):
    response = await create_user(name="     ", email="x@example.com")
    assert response.status_code == 400
    assert response.json()["message"] == "Name must contain at least one alphanumeric character."


async def test_create_user_rejects_invalid_email(create_user):
    response = await create_user(name="Valid Name", email="not-an-email")
    assert response.status_code == 400


async def test_create_user_rejects_missing_email(client):
    response = await client.post(
        "/users",
        json={"name": "Valid Name", "timezone": "UTC"},
    )
    assert response.status_code == 400


async def test_create_user_rejects_oversized_name(create_user):
    response = await create_user(name="x" * 101, email="x@example.com")
    assert response.status_code == 400


async def test_get_user_returns_created_user(create_user, client):
    created = (await create_user(name="Found", email="found@example.com")).json()["data"]
    response = await client.get(f"/users/{created['id']}")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["id"] == created["id"]
    assert body["name"] == "Found"


async def test_get_user_not_found(client):
    response = await client.get(f"/users/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["success"] is False
    assert response.json()["message"] == "User not found."


async def test_get_user_malformed_id_rejected(client):
    response = await client.get("/users/not-a-uuid")
    assert response.status_code == 400


async def test_list_users_paginates(create_user, client):
    for index in range(4):
        response = await create_user(name=f"User {index}", email=f"u{index}@example.com")
        assert response.status_code == 201, response.text

    first_page = await client.get("/users", params={"page": 1, "size": 2})
    assert first_page.status_code == 200
    meta = first_page.json()["data"]["meta"]
    assert meta["total"] == 4
    assert meta["total_pages"] == 2
    assert len(first_page.json()["data"]["items"]) == 2

    second_page = await client.get("/users", params={"page": 2, "size": 2})
    assert len(second_page.json()["data"]["items"]) == 2


async def test_list_users_invalid_page_size_rejected(client):
    response = await client.get("/users", params={"size": 200})
    assert response.status_code == 400


async def test_update_user_updates_name_and_regenerates_slug(create_user, client):
    created = (await create_user(name="Old Name", email="u@example.com")).json()["data"]
    response = await client.patch(
        f"/users/{created['id']}",
        json={"name": "New Name"},
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["name"] == "New Name"
    assert body["slug"] == "new-name"


async def test_update_user_updates_email_and_timezone(create_user, client):
    created = (await create_user(name="Host", email="old@example.com")).json()["data"]
    response = await client.patch(
        f"/users/{created['id']}",
        json={"email": "new@example.com", "timezone": "UTC"},
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["email"] == "new@example.com"
    assert body["timezone"] == "UTC"


async def test_update_user_email_conflict(create_user, client):
    first = (await create_user(name="First", email="first@example.com")).json()["data"]
    second = (await create_user(name="Second", email="second@example.com")).json()["data"]
    response = await client.patch(
        f"/users/{second['id']}",
        json={"email": "first@example.com"},
    )
    assert response.status_code == 409
    assert response.json()["message"] == "Email already exists."


async def test_update_user_not_found(client):
    response = await client.patch(f"/users/{uuid4()}", json={"name": "Anything"})
    assert response.status_code == 404


async def test_delete_user_removes_user(create_user, client, db):
    created = (await create_user(name="Gone", email="gone@example.com")).json()["data"]
    response = await client.delete(f"/users/{created['id']}")
    assert response.status_code == 200
    assert response.json()["success"] is True

    after = await client.get(f"/users/{created['id']}")
    assert after.status_code == 404

    rows = await db("SELECT id FROM users WHERE id = :uid", {"uid": created["id"]})
    assert rows == []


async def test_delete_user_not_found(client):
    response = await client.delete(f"/users/{uuid4()}")
    assert response.status_code == 404