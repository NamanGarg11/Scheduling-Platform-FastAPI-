from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import TimestampMixin, UUIDMixin
from app.slots.enums import SlotStatus


class Slot(
    UUIDMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "slots"

    __table_args__ = (
        UniqueConstraint(
            "event_type_id",
            "start_at",
            "end_at",
            name="uq_slot_event_type_start_end",
        ),
        Index(
            "ix_slots_host_start_at",
            "host_id",
            "start_at",
        ),
        Index(
            "ix_slots_status",
            "status",
        ),
    )

    host_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    event_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "event_types.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    status: Mapped[SlotStatus] = mapped_column(
        SQLEnum(
            SlotStatus,
            name="slotstatus",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=SlotStatus.AVAILABLE,
    )