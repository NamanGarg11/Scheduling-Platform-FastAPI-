from datetime import date, time
from uuid import UUID

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Time,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.availability.exceptions.enums import AvailabilityExceptionKind
from app.core.database.base import Base
from app.core.database.mixins import TimestampMixin, UUIDMixin


class AvailabilityException(
    UUIDMixin,
    TimestampMixin,
    Base,
):
    """A one-off override of a host's recurring availability (ADR-019).

    ``BLOCK_FULL_DAY`` rows have NULL ``start_time``/``end_time``;
    ``BLOCK_PARTIAL`` and ``ADD_WINDOW`` require both.
    """

    __tablename__ = "availability_exceptions"

    __table_args__ = (
        UniqueConstraint(
            "host_id",
            "exception_date",
            "kind",
            "start_time",
            "end_time",
            name="uq_availability_exception_host_date_kind_times",
        ),
        Index(
            "ix_availability_exceptions_host_date",
            "host_id",
            "exception_date",
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

    exception_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    kind: Mapped[AvailabilityExceptionKind] = mapped_column(
        SQLEnum(
            AvailabilityExceptionKind,
            name="availabilityexceptionkind",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    start_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    end_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )
