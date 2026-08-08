from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.bookings.enums import BookingStatus
from app.bookings.model import Booking
from app.bookings.repository import BookingRepository
from app.bookings.schema import CreateBookingRequest
from app.core.exceptions.base import NotFoundException, ValidationException
from app.core.logging import get_logger
from app.slots.enums import SlotStatus
from app.users.repository import UserRepository

logger = get_logger(__name__)


class BookingService:

    def __init__(
        self,
        repository: BookingRepository,
        user_repository: UserRepository,
    ) -> None:
        self.repository = repository
        self.user_repository = user_repository

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> Booking:

        logger.info(
            "Creating booking for slot %s by %s <%s>.",
            request.slot_id,
            request.invitee_name,
            request.invitee_email,
        )

        # ---------------------------------------------------------
        # 1. Lock slot (pessimistic strategy).
        # ---------------------------------------------------------
        slot = await self.repository.find_slot_for_update(
            request.slot_id,
        )

        if slot is None:

            logger.warning(
                "Booking failed. Slot %s not found.",
                request.slot_id,
            )

            raise NotFoundException(
                "Slot not found.",
            )

        # ---------------------------------------------------------
        # 2. Check the slot has not already started.
        # ---------------------------------------------------------
        if slot.start_at is not None and slot.start_at <= datetime.now(
            timezone.utc,
        ):

            logger.warning(
                "Booking rejected. Slot %s already started at %s.",
                slot.id,
                slot.start_at,
            )

            raise ValidationException(
                "Slot has already started.",
            )

        # ---------------------------------------------------------
        # 3. Check availability.
        # ---------------------------------------------------------
        if slot.status != SlotStatus.AVAILABLE:

            logger.warning(
                "Booking rejected. Slot %s is already %s.",
                slot.id,
                slot.status.value,
            )

            raise ValidationException(
                "Slot is not available.",
            )

        # ---------------------------------------------------------
        # 4. Prevent host self-booking by email.
        # ---------------------------------------------------------
        host = await self.user_repository.find_by_id(
            slot.host_id,
        )

        if (
            host is not None
            and host.email.casefold() == str(request.invitee_email).casefold()
        ):

            logger.warning(
                "Host %s attempted to book own slot %s.",
                host.id,
                slot.id,
            )

            raise ValidationException(
                "Host cannot book their own slot.",
            )

        # ---------------------------------------------------------
        # 5. Build booking.
        # ---------------------------------------------------------
        booking = Booking(
            slot_id=slot.id,
            host_id=slot.host_id,
            event_type_id=slot.event_type_id,
            invitee_email=str(request.invitee_email),
            invitee_name=request.invitee_name,
            invitee_notes=request.invitee_notes,
            status=BookingStatus.CONFIRMED,
        )

        try:

            saved_booking = await self.repository.save(
                booking,
            )

            # -----------------------------------------------------
            # 6. Consume the slot.
            # -----------------------------------------------------
            slot.status = SlotStatus.BOOKED

            await self.repository.session.flush()

        except IntegrityError as exc:

            logger.exception(
                "Database conflict while booking slot %s.",
                slot.id,
            )

            raise ValidationException(
                "Slot is not available.",
            ) from exc

        logger.info(
            "Booking %s created successfully for slot %s.",
            saved_booking.id,
            slot.id,
        )

        return saved_booking

    async def list_bookings(
        self,
        host_id: UUID,
    ) -> list[Booking]:

        logger.debug(
            "Fetching bookings for host %s.",
            host_id,
        )

        return await self.repository.find_by_host(
            host_id,
        )
