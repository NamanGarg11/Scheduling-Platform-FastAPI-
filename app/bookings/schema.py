from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

if TYPE_CHECKING:
    from app.bookings.model import Booking

from app.bookings.enums import BookingStatus


class CreateBookingRequest(
    BaseModel,
):
    model_config = ConfigDict(
        extra="forbid",
    )

    slot_id: UUID

    invitee_email: EmailStr

    invitee_name: str = Field(
        min_length=1,
        max_length=100,
    )

    invitee_notes: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "invitee_name",
    )
    @classmethod
    def validate_invitee_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Invitee name cannot be blank.",
            )

        return value

    @field_validator(
        "invitee_notes",
    )
    @classmethod
    def validate_invitee_notes(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return value


class EventTypeBrief(
    BaseModel,
):
    id: UUID
    title: str
    slug: str
    duration_minutes: int


class BookingResponse(
    BaseModel,
):
    id: UUID
    slot_id: UUID
    host_id: UUID
    event_type_id: UUID
    invitee_email: EmailStr
    invitee_name: str
    invitee_notes: str | None = None
    status: BookingStatus
    start_at: datetime
    end_at: datetime
    event_type: EventTypeBrief
    meet_link: str | None = None
    calendar_event_id: str | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


def build_booking_response(
    booking: "Booking",
) -> BookingResponse:
    """Serialize a booking together with its slot window and event type."""
    slot = booking.slot
    event_type = booking.event_type

    if slot is None or event_type is None:
        raise ValueError(
            "Booking is missing its slot or event type.",
        )

    return BookingResponse(
        id=booking.id,
        slot_id=booking.slot_id,
        host_id=booking.host_id,
        event_type_id=booking.event_type_id,
        invitee_email=booking.invitee_email,
        invitee_name=booking.invitee_name,
        invitee_notes=booking.invitee_notes,
        status=booking.status,
        start_at=slot.start_at,
        end_at=slot.end_at,
        event_type=EventTypeBrief(
            id=event_type.id,
            title=event_type.title,
            slug=event_type.slug,
            duration_minutes=event_type.duration_minutes,
        ),
        meet_link=booking.meet_link,
        calendar_event_id=booking.calendar_event_id,
        cancelled_at=booking.cancelled_at,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )
