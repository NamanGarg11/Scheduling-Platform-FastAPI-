import os
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/scheduling_platform_test",
)
os.environ["ENVIRONMENT"] = "testing"

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text

from app.config.database import engine
from app.main import app


@pytest.fixture(autouse=True)
async def clean_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


@pytest.fixture
async def db() -> object:
    async def _run(stmt: str, params: dict | None = None) -> list[tuple]:
        async with engine.begin() as conn:
            result = await conn.execute(text(stmt), params or {})
            return list(result.fetchall())

    return _run


@pytest.fixture
async def create_user(client: httpx.AsyncClient) -> object:
    async def _make(
        name: str = "Host One",
        email: str | None = None,
        timezone: str = "Asia/Kolkata",
        **overrides: object,
    ) -> httpx.Response:
        email = email or f"host-{uuid4_hex()}@example.com"
        payload: dict = {
            "name": name,
            "email": email,
            "timezone": timezone,
        }
        payload.update(overrides)
        return await client.post("/users", json=payload)

    return _make


@pytest.fixture
async def create_event_type(client: httpx.AsyncClient) -> object:
    async def _make(
        host_id: str,
        *,
        title: str = "Consultation",
        description: str | None = None,
        duration_minutes: int = 30,
        location_type: str = "zoom",
        location_value: str | None = None,
        buffer_before_minutes: int = 0,
        buffer_after_minutes: int = 0,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        payload: dict = {
            "title": title,
            "duration_minutes": duration_minutes,
            "location_type": location_type,
            "location_value": location_value,
            "buffer_before_minutes": buffer_before_minutes,
            "buffer_after_minutes": buffer_after_minutes,
        }
        if description is not None:
            payload["description"] = description
        request_headers = {"x-user-id": str(host_id)}
        if headers:
            request_headers.update(headers)
        return await client.post("/event-types", json=payload, headers=request_headers)

    return _make


@pytest.fixture
async def create_availability(client: httpx.AsyncClient) -> object:
    async def _make(
        host_id: str,
        *,
        day_of_week: str = "MONDAY",
        start_time: str = "09:00",
        end_time: str = "12:00",
        is_available: bool = True,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        payload: dict = {
            "day_of_week": day_of_week,
            "start_time": start_time,
            "end_time": end_time,
            "is_available": is_available,
        }
        request_headers = {"x-user-id": str(host_id)}
        if headers:
            request_headers.update(headers)
        return await client.post("/availability", json=payload, headers=request_headers)

    return _make


@pytest.fixture
async def generate_slots(client: httpx.AsyncClient) -> object:
    async def _make(
        event_type_id: str,
        start_date: date,
        end_date: date,
        **overrides: object,
    ) -> httpx.Response:
        payload: dict = {
            "event_type_id": str(event_type_id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        payload.update(overrides)
        return await client.post("/api/v1/slots/generate", json=payload)

    return _make


@pytest.fixture
async def host(client: httpx.AsyncClient, create_user) -> dict:
    response = await create_user(name="Host One", email="host-one@example.com")
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.fixture
async def second_host(client: httpx.AsyncClient, create_user) -> dict:
    response = await create_user(name="Host Two", email="host-two@example.com")
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.fixture
async def slots_env(
    client: httpx.AsyncClient,
    host: dict,
    create_event_type,
    create_availability,
) -> dict:
    event_response = await create_event_type(
        host["id"],
        title="Consultation",
        duration_minutes=30,
        buffer_before_minutes=5,
        buffer_after_minutes=10,
    )
    assert event_response.status_code == 201, event_response.text
    event_type = event_response.json()

    availability_response = await create_availability(
        host["id"],
        day_of_week="MONDAY",
        start_time="09:00",
        end_time="12:00",
    )
    assert availability_response.status_code == 201, availability_response.text

    return {
        "host": host,
        "host_id": host["id"],
        "event_type": event_type,
        "event_type_id": event_type["id"],
    }


@pytest.fixture
async def slot_maker(
    create_event_type,
    create_availability,
    generate_slots,
) -> object:
    async def _make(
        host: dict,
        *,
        day: str = "MONDAY",
        start: str = "09:00",
        end: str = "12:00",
        duration_minutes: int = 30,
        buffer_before_minutes: int = 0,
        buffer_after_minutes: int = 0,
        start_date: date | None = None,
        end_date: date | None = None,
        title: str = "Test Event",
    ) -> tuple[dict, httpx.Response]:
        event_response = await create_event_type(
            host["id"],
            title=title,
            duration_minutes=duration_minutes,
            buffer_before_minutes=buffer_before_minutes,
            buffer_after_minutes=buffer_after_minutes,
        )
        assert event_response.status_code == 201, event_response.text
        event_type = event_response.json()

        availability_response = await create_availability(
            host["id"],
            day_of_week=day,
            start_time=start,
            end_time=end,
        )
        assert availability_response.status_code == 201, availability_response.text

        target_start = start_date or _today_monday()
        target_end = end_date or target_start
        generation = await generate_slots(
            event_type["id"],
            target_start,
            target_end,
        )
        return event_type, generation

    return _make


@dataclass(frozen=True)
class MondayWindow:
    monday: date
    tuesday: date


@pytest.fixture(scope="session")
def window_dates() -> MondayWindow:
    monday = _today_monday()
    return MondayWindow(monday=monday, tuesday=monday + timedelta(days=1))


def _today_monday() -> date:
    today = date.today()
    days_until_monday = (0 - today.weekday()) % 7
    monday = today + timedelta(days=days_until_monday)
    if monday == today:
        monday += timedelta(days=7)
    return monday


def uuid4_hex() -> str:
    import uuid

    return uuid.uuid4().hex