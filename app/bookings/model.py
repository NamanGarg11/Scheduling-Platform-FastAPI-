from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.bookings.enums import BookingStatus
from app.core.database.base import Base
from app.core.database.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.event_types.model import EventType
    from app.slots.model import Slot
    from app.users.model import User


class Booking(
    UUIDMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "bookings"

    __table_args__ = (
        Index(
            "ix_bookings_host_id",
            "host_id",
        ),
        Index(
            "ix_bookings_event_type_id",
            "event_type_id",
        ),
        Index(
            "ix_bookings_status",
            "status",
        ),
        Index(
            "ix_bookings_slot_id",
            "slot_id",
        ),
        Index(
            "uq_bookings_confirmed_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
        ),
    )

    slot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "slots.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    host_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    event_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "event_types.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    invitee_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    invitee_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    invitee_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[BookingStatus] = mapped_column(
        SQLEnum(
            BookingStatus,
            name="bookingstatus",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=BookingStatus.CONFIRMED,
    )

    meet_link: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    calendar_event_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    slot: Mapped["Slot"] = relationship(
        lazy="selectin",
    )

    host: Mapped["User"] = relationship(
        foreign_keys=[host_id],
        lazy="selectin",
    )

    event_type: Mapped["EventType"] = relationship(
        lazy="selectin",
    )
