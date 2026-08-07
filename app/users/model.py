from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import Base
from app.core.database.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.event_types.model import EventType


class User(
    UUIDMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    slug: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        unique=True,
        index=True,
    )

    timezone: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="UTC",
    )

    event_types: Mapped[list["EventType"]] = relationship(
        back_populates="host",
        cascade="all, delete-orphan",
        lazy="selectin",
    )