from datetime import time
from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.availability.enums import DayOfWeek
from app.core.database.base import Base
from app.core.database.mixins import (
    TimestampMixin,
    UUIDMixin,
)
class Availability(
    UUIDMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "availability"

    __table_args__ = (
        UniqueConstraint(
            "host_id",
            "day_of_week",
            name="uq_availability_host_day",
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

    day_of_week: Mapped[DayOfWeek]

    start_time: Mapped[time] = mapped_column(
        Time(),
        nullable=False,
    )

    end_time: Mapped[time] = mapped_column(
        Time(),
        nullable=False,
    )

    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )