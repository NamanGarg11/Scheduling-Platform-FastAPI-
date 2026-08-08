from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import Base
from app.core.database.mixins import TimestampMixin, UUIDMixin
from app.users.model import User


class EventType(
    UUIDMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "event_types"

    __table_args__ = (
        UniqueConstraint(
            "host_id",
            "slug",
            name="uq_event_type_host_slug",
        ),
    )

    host_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    slug: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    location_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    location_value: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    buffer_before_minutes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    buffer_after_minutes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    host: Mapped["User"] = relationship(
        back_populates="event_types",
        lazy="selectin",
    )