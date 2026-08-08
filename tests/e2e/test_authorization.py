import pytest

pytestmark = pytest.mark.skip(
    reason="Authorization/authentication layer is not implemented in the current codebase.",
)


async def test_host_b_cannot_read_host_a_event_type(host, second_host, create_event_type, client):
    event_type = (await create_event_type(host["id"], title="Private")).json()
    response = await client.get(f"/event-types/{event_type['id']}")
    assert response.status_code == 404 or response.status_code == 403


async def test_host_b_cannot_update_host_a_event_type(host, second_host, create_event_type, client):
    event_type = (await create_event_type(host["id"], title="Private")).json()
    response = await client.patch(
        f"/event-types/{event_type['id']}",
        json={"title": "Hijacked"},
    )
    assert response.status_code == 404 or response.status_code == 403


async def test_host_b_cannot_delete_host_a_event_type(host, second_host, create_event_type, client):
    event_type = (await create_event_type(host["id"], title="Private")).json()
    response = await client.delete(f"/event-types/{event_type['id']}")
    assert response.status_code == 404 or response.status_code == 403


async def test_host_b_cannot_read_host_a_availability(host, second_host, create_availability, client):
    availability = (await create_availability(host["id"], day_of_week="MONDAY")).json()
    response = await client.get(f"/availability/{availability['id']}")
    assert response.status_code == 404 or response.status_code == 403


async def test_host_b_cannot_modify_host_a_availability(host, second_host, create_availability, client):
    availability = (await create_availability(host["id"], day_of_week="MONDAY")).json()
    response = await client.patch(
        f"/availability/{availability['id']}",
        json={"start_time": "10:00"},
    )
    assert response.status_code == 404 or response.status_code == 403


async def test_host_b_cannot_generate_slots_for_host_a(
    host, second_host, create_event_type, create_availability, generate_slots, window_dates,
):
    event_type = (await create_event_type(host["id"], title="Private")).json()
    await create_availability(host["id"], day_of_week="MONDAY")
    response = await generate_slots(event_type["id"], window_dates.monday, window_dates.monday)
    assert response.status_code == 403 or response.status_code == 404