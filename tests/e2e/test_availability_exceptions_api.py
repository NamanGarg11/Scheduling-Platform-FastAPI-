"""API tests for availability exceptions (real app + Postgres).

Requires a running Postgres with migrations applied (see tests/e2e/conftest.py).
"""

from uuid import uuid4

import pytest


@pytest.fixture
async def create_exception(client) -> object:
    async def _make(
        host_id: str,
        *,
        kind: str = "BLOCK_PARTIAL",
        exception_date: str = "2026-08-17",
        start_time: str | None = "12:00",
        end_time: str | None = "14:00",
        headers: dict[str, str] | None = None,
    ) -> object:
        payload: dict = {
            "kind": kind,
            "date": exception_date,
        }
        if start_time is not None:
            payload["start_time"] = start_time
        if end_time is not None:
            payload["end_time"] = end_time
        request_headers = {"x-user-id": str(host_id)}
        if headers:
            request_headers.update(headers)
        return await client.post(
            "/availability/exceptions",
            json=payload,
            headers=request_headers,
        )

    return _make


async def test_create_exception_returns_201_with_shape(
    client,
    host,
    create_exception,
):
    response = await create_exception(
        host["id"],
        kind="BLOCK_PARTIAL",
        exception_date="2026-08-17",
        start_time="12:00",
        end_time="14:00",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"]
    assert body["host_id"] == host["id"]
    assert body["kind"] == "BLOCK_PARTIAL"
    assert body["date"] == "2026-08-17"
    assert body["start_time"] == "12:00:00"
    assert body["end_time"] == "14:00:00"


async def test_create_full_day_block(
    client,
    host,
    create_exception,
):
    response = await create_exception(
        host["id"],
        kind="BLOCK_FULL_DAY",
        exception_date="2026-08-17",
        start_time=None,
        end_time=None,
    )
    assert response.status_code == 201, response.text
    assert response.json()["start_time"] is None
    assert response.json()["end_time"] is None


async def test_create_add_window(
    client,
    host,
    create_exception,
):
    response = await create_exception(
        host["id"],
        kind="ADD_WINDOW",
        exception_date="2026-08-18",
        start_time="18:00",
        end_time="20:00",
    )
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "ADD_WINDOW"


async def test_create_duplicate_raises_409(
    client,
    host,
    create_exception,
):
    await create_exception(host["id"])
    response = await create_exception(host["id"])
    assert response.status_code == 409, response.text
    assert response.json()["success"] is False


async def test_create_partial_without_times_raises_400(
    client,
    host,
    create_exception,
):
    # The centralized exception handler maps RequestValidationError -> 400
    # (project convention, same as the booking contract).
    response = await create_exception(
        host["id"],
        start_time=None,
        end_time=None,
    )
    assert response.status_code == 400, response.text


async def test_create_full_day_with_times_raises_400(
    client,
    host,
    create_exception,
):
    response = await create_exception(
        host["id"],
        kind="BLOCK_FULL_DAY",
    )
    assert response.status_code == 400, response.text


async def test_create_inverted_times_raises_400(
    client,
    host,
    create_exception,
):
    response = await create_exception(
        host["id"],
        start_time="14:00",
        end_time="12:00",
    )
    assert response.status_code == 400, response.text


async def test_create_extra_field_raises_400(
    client,
    host,
    create_exception,
):
    response = await client.post(
        "/availability/exceptions",
        json={
            "kind": "BLOCK_PARTIAL",
            "date": "2026-08-17",
            "start_time": "12:00",
            "end_time": "14:00",
            "unexpected": True,
        },
        headers={"x-user-id": str(host["id"])},
    )
    assert response.status_code == 400, response.text


async def test_create_unknown_host_raises_404(
    client,
    create_exception,
):
    response = await create_exception(str(uuid4()))
    assert response.status_code == 404, response.text


async def test_list_exceptions_is_host_scoped(
    client,
    host,
    second_host,
    create_exception,
):
    await create_exception(host["id"], exception_date="2026-08-17")
    await create_exception(
        second_host["id"],
        exception_date="2026-08-18",
    )

    response = await client.get(
        "/availability/exceptions",
        headers={"x-user-id": str(host["id"])},
    )
    assert response.status_code == 200, response.text
    bodies = response.json()
    assert len(bodies) == 1
    assert all(item["host_id"] == host["id"] for item in bodies)


async def test_get_exception_by_id(
    client,
    host,
    create_exception,
):
    created = (await create_exception(host["id"])).json()

    response = await client.get(f"/availability/exceptions/{created['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == created["id"]


async def test_get_missing_exception_raises_404(client):
    response = await client.get(f"/availability/exceptions/{uuid4()}")
    assert response.status_code == 404, response.text


async def test_patch_exception(
    client,
    host,
    create_exception,
):
    created = (await create_exception(host["id"])).json()

    response = await client.patch(
        f"/availability/exceptions/{created['id']}",
        json={"kind": "BLOCK_FULL_DAY", "start_time": None, "end_time": None},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "BLOCK_FULL_DAY"
    assert body["start_time"] is None
    assert body["end_time"] is None


async def test_patch_to_duplicate_raises_409(
    client,
    host,
    create_exception,
):
    first = (await create_exception(
        host["id"],
        exception_date="2026-08-17",
    )).json()
    second = (await create_exception(
        host["id"],
        exception_date="2026-08-18",
    )).json()

    response = await client.patch(
        f"/availability/exceptions/{second['id']}",
        json={"date": "2026-08-17"},
    )
    assert response.status_code == 409, response.text
    assert first["id"] != second["id"]


async def test_delete_exception_returns_204(
    client,
    host,
    create_exception,
):
    created = (await create_exception(host["id"])).json()

    response = await client.delete(
        f"/availability/exceptions/{created['id']}",
    )
    assert response.status_code == 204, response.text

    get_response = await client.get(
        f"/availability/exceptions/{created['id']}",
    )
    assert get_response.status_code == 404
