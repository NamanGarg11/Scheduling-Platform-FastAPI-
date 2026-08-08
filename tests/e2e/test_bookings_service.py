import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.bookings.enums import BookingStatus
from app.bookings.repository import BookingRepository
from app.bookings.schema import CreateBookingRequest
from app.bookings.service import BookingService
from app.core.exceptions.base import NotFoundException, ValidationException
from app.slots.enums import SlotStatus
from app.slots.model import Slot
from app.users.model import User
from app.users.repository import UserRepository


def make_host(host_id: object | None = None) -> User:
    return User(
        id=host_id or uuid4(),
        name="Host",
        email=f"host-{uuid4().hex}@example.com",
        slug=f"host-{uuid4().hex}",
        timezone="UTC",
    )


def make_slot(
    host_id: object | None = None,
    event_type_id: object | None = None,
    status: SlotStatus = SlotStatus.AVAILABLE,
    start_offset: timedelta | None = None,
) -> Slot:
    now = datetime.now(timezone.utc)
    slot = Slot(
        id=uuid4(),
        host_id=host_id or uuid4(),
        event_type_id=event_type_id or uuid4(),
        start_at=now + (start_offset or timedelta(days=1)),
        end_at=now + (start_offset or timedelta(days=1)) + timedelta(minutes=30),
        status=status,
    )
    return slot


def make_request(
    slot_id: object, email: str, name: str = "Bob"
) -> CreateBookingRequest:
    return CreateBookingRequest(
        slot_id=slot_id,
        invitee_email=email,
        invitee_name=name,
        invitee_notes=None,
    )


def build_service(
    *,
    slot: Slot | None,
    host: User | None = None,
    save_error: Exception | None = None,
) -> tuple[BookingService, AsyncMock, AsyncMock]:
    repo = AsyncMock(spec=BookingRepository)
    repo.find_slot_for_update = AsyncMock(return_value=slot)
    repo.save = AsyncMock(side_effect=save_error)
    repo.session = AsyncMock()
    repo.session.flush = AsyncMock()

    async def save(booking):
        return booking

    if save_error is None:
        repo.save.side_effect = None
        repo.save = AsyncMock(side_effect=save)

    user_repo = AsyncMock(spec=UserRepository)
    user_repo.find_by_id = AsyncMock(return_value=host)

    service = BookingService(
        repository=repo,
        user_repository=user_repo,
    )
    return service, repo, user_repo


async def test_successful_booking_flow():
    slot = make_slot()
    service, repo, _ = build_service(slot=slot)

    result = await service.create_booking(make_request(slot.id, "bob@example.com"))

    assert result is not None
    assert result.slot_id == slot.id
    assert result.host_id == slot.host_id
    assert result.event_type_id == slot.event_type_id
    assert result.invitee_email == "bob@example.com"
    assert result.invitee_name == "Bob"
    assert result.status == BookingStatus.CONFIRMED
    assert slot.status == SlotStatus.BOOKED
    repo.session.flush.assert_awaited()


async def test_host_id_derived_from_slot():
    host_id = uuid4()
    slot = make_slot(host_id=host_id)
    service, _, _ = build_service(slot=slot)

    result = await service.create_booking(make_request(slot.id, "bob@example.com"))

    assert result.host_id == host_id


async def test_event_type_id_derived_from_slot():
    event_type_id = uuid4()
    slot = make_slot(event_type_id=event_type_id)
    service, _, _ = build_service(slot=slot)

    result = await service.create_booking(make_request(slot.id, "bob@example.com"))

    assert result.event_type_id == event_type_id


async def test_slot_not_found_raises_404():
    service, repo, _ = build_service(slot=None)

    try:
        await service.create_booking(make_request(uuid4(), "bob@example.com"))
        raise AssertionError("expected NotFoundException")
    except NotFoundException as exc:
        assert exc.status_code == 404
        assert exc.message == "Slot not found."


async def test_slot_already_started_raises_400():
    slot = make_slot(
        start_offset=timedelta(minutes=-30),
    )
    service, _, _ = build_service(slot=slot)

    try:
        await service.create_booking(make_request(slot.id, "bob@example.com"))
        raise AssertionError("expected ValidationException")
    except ValidationException as exc:
        assert exc.status_code == 400
        assert "started" in exc.message
    assert slot.status == SlotStatus.AVAILABLE


async def test_slot_already_booked_raises_400():
    slot = make_slot(status=SlotStatus.BOOKED)
    service, _, _ = build_service(slot=slot)

    try:
        await service.create_booking(make_request(slot.id, "bob@example.com"))
        raise AssertionError("expected ValidationException")
    except ValidationException as exc:
        assert exc.status_code == 400
        assert "not available" in exc.message
    assert slot.status == SlotStatus.BOOKED


async def test_slot_blocked_raises_400():
    slot = make_slot(status=SlotStatus.BLOCKED)
    service, _, _ = build_service(slot=slot)

    try:
        await service.create_booking(make_request(slot.id, "bob@example.com"))
        raise AssertionError("expected ValidationException")
    except ValidationException as exc:
        assert exc.status_code == 400


async def test_host_self_booking_raises_400():
    host = make_host()
    slot = make_slot(host_id=host.id)
    service, _, _ = build_service(slot=slot, host=host)

    try:
        await service.create_booking(
            make_request(slot.id, host.email.upper()),
        )
        raise AssertionError("expected ValidationException")
    except ValidationException as exc:
        assert exc.status_code == 400
        assert "own slot" in exc.message
    assert slot.status == SlotStatus.AVAILABLE


async def test_repository_save_failure_propagates():
    slot = make_slot()
    service, _, _ = build_service(
        slot=slot,
        save_error=RuntimeError("boom"),
    )

    try:
        await service.create_booking(make_request(slot.id, "bob@example.com"))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert str(exc) == "boom"


async def test_integrity_error_converted_to_400():
    slot = make_slot()
    service, _, _ = build_service(
        slot=slot,
        save_error=IntegrityError("INSERT", {}, Exception("dup")),
    )

    try:
        await service.create_booking(make_request(slot.id, "bob@example.com"))
        raise AssertionError("expected ValidationException")
    except ValidationException as exc:
        assert exc.status_code == 400


async def test_success_logs_info(caplog):
    slot = make_slot()
    service = build_service(slot=slot)[0]

    with caplog.at_level(logging.INFO, logger="app.bookings.service"):
        await service.create_booking(make_request(slot.id, "bob@example.com"))

    joined = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == "app.bookings.service"
    )
    assert "created successfully" in joined


async def test_expected_failure_logs_warning(caplog):
    slot = make_slot(status=SlotStatus.BOOKED)
    service, _, _ = build_service(slot=slot)

    with caplog.at_level(logging.WARNING, logger="app.bookings.service"):
        try:
            await service.create_booking(make_request(slot.id, "bob@example.com"))
        except ValidationException:
            pass

    joined = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == "app.bookings.service"
    )
    assert "already" in joined or "not available" in joined


async def test_list_bookings_delegates_to_host():
    slot = make_slot()
    service, repo, _ = build_service(slot=slot)
    repo.find_by_host = AsyncMock(return_value=[make_booking(slot)])

    result = await service.list_bookings(uuid4())

    assert len(result) == 1
    repo.find_by_host.assert_awaited()


def make_booking(slot: Slot) -> object:
    from app.bookings.model import Booking

    return Booking(
        id=uuid4(),
        slot_id=slot.id,
        host_id=slot.host_id,
        event_type_id=slot.event_type_id,
        invitee_email="bob@example.com",
        invitee_name="Bob",
        invitee_notes=None,
        status=BookingStatus.CONFIRMED,
    )
