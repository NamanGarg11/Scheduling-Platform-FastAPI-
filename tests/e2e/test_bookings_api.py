from datetime import date
from uuid import uuid4

from app.slots.enums import SlotStatus


async def book(client, slot_id, **extra):
    payload = {
        "slot_id": str(slot_id),
        "invitee_email": "invitee@example.com",
        "invitee_name": "Invitee",
        "invitee_notes": None,
    }
    payload.update(extra)
    return await client.post("/bookings", json=payload)


async def make_bookable_slot(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    return await make_host_and_slot(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )


async def make_host_and_slot(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    host = (
        await create_user(
            name="Host One", email=f"slot-host-{uuid4().hex[:8]}@example.com"
        )
    ).json()["data"]
    event_type = (
        await create_event_type(host["id"], title="Bookable", duration_minutes=30)
    ).json()
    await create_availability(host["id"], day_of_week="MONDAY")
    generation = await generate_slots(
        event_type["id"],
        window_dates.monday,
        window_dates.monday,
    )
    assert generation.status_code == 201, generation.text
    slot = generation.json()["slots"][0]
    return {"host": host, "event_type": event_type, "slot": slot}


async def test_create_booking_success(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    ctx = await make_bookable_slot(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    slot = ctx["slot"]

    response = await client.post(
        "/bookings",
        json={
            "slot_id": slot["id"],
            "invitee_email": "bob@example.com",
            "invitee_name": "Bob",
            "invitee_notes": "Looking forward",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slot_id"] == slot["id"]
    assert body["host_id"] == ctx["host"]["id"]
    assert body["event_type_id"] == ctx["event_type"]["id"]
    assert body["invitee_email"] == "bob@example.com"
    assert body["invitee_name"] == "Bob"
    assert body["invitee_notes"] == "Looking forward"
    assert body["status"] == "confirmed"
    assert "start_at" in body
    assert "end_at" in body
    assert body["event_type"]["id"] == ctx["event_type"]["id"]
    assert body["event_type"]["title"] == "Bookable"
    assert "meet_link" in body
    assert body["meet_link"] is None
    assert "calendar_event_id" in body
    assert "cancelled_at" in body
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_create_booking_persists_correct_state(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    ctx = await make_bookable_slot(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    slot = ctx["slot"]

    response = await client.post(
        "/bookings",
        json={
            "slot_id": slot["id"],
            "invitee_email": "alice@example.com",
            "invitee_name": "Alice",
            "invitee_notes": None,
        },
    )
    assert response.status_code == 201, response.text
    booking = response.json()

    rows = await db(
        """
        SELECT slot_id, host_id, event_type_id, invitee_email,
               invitee_name, status
        FROM bookings WHERE id = :id
        """,
        {"id": booking["id"]},
    )
    assert len(rows) == 1
    assert str(rows[0][0]) == slot["id"]
    assert str(rows[0][1]) == ctx["host"]["id"]
    assert str(rows[0][2]) == ctx["event_type"]["id"]
    assert rows[0][3] == "alice@example.com"
    assert rows[0][4] == "Alice"
    assert rows[0][5] == "confirmed"

    slot_rows = await db(
        "SELECT status FROM slots WHERE id = :id",
        {"id": slot["id"]},
    )
    assert slot_rows[0][0] == "BOOKED"


async def test_missing_slot_id_validation(client):
    response = await client.post(
        "/bookings",
        json={"invitee_email": "x@example.com", "invitee_name": "X"},
    )
    assert response.status_code == 400


async def test_invalid_slot_uuid_rejected(client):
    response = await client.post(
        "/bookings",
        json={
            "slot_id": "not-a-uuid",
            "invitee_email": "x@example.com",
            "invitee_name": "X",
        },
    )
    assert response.status_code == 400


async def test_missing_invitee_email_rejected(client):
    response = await client.post(
        "/bookings",
        json={"slot_id": str(uuid4()), "invitee_name": "X"},
    )
    assert response.status_code == 400


async def test_invalid_invitee_email_rejected(client):
    response = await client.post(
        "/bookings",
        json={
            "slot_id": str(uuid4()),
            "invitee_email": "not-an-email",
            "invitee_name": "X",
        },
    )
    assert response.status_code == 400


async def test_missing_invitee_name_rejected(client):
    response = await client.post(
        "/bookings",
        json={"slot_id": str(uuid4()), "invitee_email": "x@example.com"},
    )
    assert response.status_code == 400


async def test_null_slot_id_rejected(client):
    response = await client.post(
        "/bookings",
        json={
            "slot_id": None,
            "invitee_email": "x@example.com",
            "invitee_name": "X",
        },
    )
    assert response.status_code == 400


async def test_empty_body_rejected(client):
    response = await client.post("/bookings", json={})
    assert response.status_code == 400


async def test_extra_fields_rejected(client):
    response = await client.post(
        "/bookings",
        json={
            "slot_id": str(uuid4()),
            "invitee_email": "x@example.com",
            "invitee_name": "X",
            "host_id": str(uuid4()),
            "status": "confirmed",
        },
    )
    assert response.status_code == 400


async def test_nonexistent_slot_returns_404(client):
    response = await client.post(
        "/bookings",
        json={
            "slot_id": str(uuid4()),
            "invitee_email": "ghost@example.com",
            "invitee_name": "Ghost",
        },
    )
    assert response.status_code == 404
    assert response.json()["success"] is False


async def test_booked_slot_returns_400_sequential(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    ctx = await make_host_and_slot(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )

    first = await client.post(
        "/bookings",
        json={
            "slot_id": ctx["slot"]["id"],
            "invitee_email": "a@example.com",
            "invitee_name": "A",
        },
    )
    assert first.status_code == 201
    second = await client.post(
        "/bookings",
        json={
            "slot_id": ctx["slot"]["id"],
            "invitee_email": "b@example.com",
            "invitee_name": "B",
        },
    )
    assert second.status_code == 400
    assert second.json()["success"] is False
    assert "not available" in second.json()["message"]


async def test_host_cannot_book_own_slot(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    ctx = await make_host_and_slot(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    response = await client.post(
        "/bookings",
        json={
            "slot_id": ctx["slot"]["id"],
            "invitee_email": ctx["host"]["email"].upper(),
            "invitee_name": "The Host",
        },
    )
    assert response.status_code == 400
    assert "own slot" in response.json()["message"]


async def test_same_invitee_books_different_slots(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    for _ in range(2):
        ctx = await make_host_and_slot(
            client,
            db,
            create_user,
            create_event_type,
            create_availability,
            generate_slots,
            window_dates,
        )
        response = await client.post(
            "/bookings",
            json={
                "slot_id": ctx["slot"]["id"],
                "invitee_email": "multi@example.com",
                "invitee_name": "Multi",
            },
        )
        assert response.status_code == 201, response.text


async def test_error_response_uses_centralized_contract(client):
    response = await client.post(
        "/bookings",
        json={
            "slot_id": str(uuid4()),
            "invitee_email": "contract@example.com",
            "invitee_name": "Contract",
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert "message" in body
    assert "details" in body


async def test_unexpected_internal_error_returns_500_safely(
    monkeypatch,
):
    async def boom(self, request):
        raise RuntimeError("boom internal")

    import app.bookings.service as bookings_service

    monkeypatch.setattr(
        bookings_service.BookingService,
        "create_booking",
        boom,
    )

    from httpx import ASGITransport

    from app.main import app

    transport = ASGITransport(
        app=app,
        raise_app_exceptions=False,
    )
    import httpx

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/bookings",
            json={
                "slot_id": str(uuid4()),
                "invitee_email": "err@example.com",
                "invitee_name": "Error",
            },
        )

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert "Traceback" not in response.text
    assert "boom internal" not in response.text


async def test_list_bookings_returns_hosts_bookings(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    ctx = await make_host_and_slot(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    first = await client.post(
        "/bookings",
        json={
            "slot_id": ctx["slot"]["id"],
            "invitee_email": "list1@example.com",
            "invitee_name": "List One",
        },
    )
    assert first.status_code == 201

    listing = await client.get(
        "/bookings",
        headers={"x-user-id": ctx["host"]["id"]},
    )
    assert listing.status_code == 200
    body = listing.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == first.json()["id"]
    assert body[0]["invitee_email"] == "list1@example.com"
    assert body[0]["start_at"] == first.json()["start_at"]


async def test_list_bookings_empty_for_unknown_host(
    client,
):
    listing = await client.get(
        "/bookings",
        headers={"x-user-id": str(uuid4())},
    )
    assert listing.status_code == 200
    assert listing.json() == []


async def test_list_bookings_requires_host_header(client):
    response = await client.get("/bookings")
    assert response.status_code == 400


async def test_host_listing_excludes_other_hosts(
    client,
    db,
    create_user,
    create_event_type,
    create_availability,
    generate_slots,
    window_dates,
):
    ctx_a = await make_host_and_slot(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    booking_a = await client.post(
        "/bookings",
        json={
            "slot_id": ctx_a["slot"]["id"],
            "invitee_email": "owned@example.com",
            "invitee_name": "Owned",
        },
    )
    assert booking_a.status_code == 201

    ctx_b = await make_host_and_slot(
        client,
        db,
        create_user,
        create_event_type,
        create_availability,
        generate_slots,
        window_dates,
    )
    await client.post(
        "/bookings",
        json={
            "slot_id": ctx_b["slot"]["id"],
            "invitee_email": "other@example.com",
            "invitee_name": "Other",
        },
    )

    listing = await client.get(
        "/bookings",
        headers={"x-user-id": ctx_a["host"]["id"]},
    )
    assert listing.status_code == 200
    body = listing.json()
    assert len(body) == 1
    assert body[0]["invitee_email"] == "owned@example.com"
