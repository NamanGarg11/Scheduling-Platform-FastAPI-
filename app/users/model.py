from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.core.database.base import Base
from app.core.database.mixins import TimestampMixin, UUIDMixin


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