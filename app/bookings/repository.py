from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.enums import BookingStatus
from app.bookings.model import Booking
from app.core.database.repository import BaseRepository
from app.slots.enums import SlotStatus
from app.slots.model import Slot


class BookingRepository(
    BaseRepository[Booking],
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(
            session,
            Booking,
        )

    async def find_by_slot(
        self,
        slot_id: UUID,
    ) -> Booking | None:
        stmt = (
            select(Booking)
            .where(
                Booking.slot_id == slot_id,
            )
            .order_by(
                Booking.created_at.desc(),
            )
        )

        result = await self.session.execute(stmt)

        return result.scalars().first()

    async def find_confirmed_by_slot(
        self,
        slot_id: UUID,
    ) -> Booking | None:
        stmt = select(Booking).where(
            Booking.slot_id == slot_id,
            Booking.status == BookingStatus.CONFIRMED,
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def find_by_host(
        self,
        host_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Booking]:
        stmt = (
            select(Booking)
            .where(
                Booking.host_id == host_id,
            )
            .order_by(
                Booking.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def count_by_host(
        self,
        host_id: UUID,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.host_id == host_id,
            )
        )

        count = await self.session.scalar(stmt)

        return int(count or 0)

    async def find_slot_for_update(
        self,
        slot_id: UUID,
    ) -> Slot | None:
        """Pessimistic strategy: lock the slot row for update."""
        stmt = (
            select(Slot)
            .where(
                Slot.id == slot_id,
            )
            .with_for_update()
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def try_occupy_slot(
        self,
        slot_id: UUID,
    ) -> bool:
        """Optimistic strategy (NOT routed): conditional UPDATE.

        Returns True only if a row was actually flipped from AVAILABLE to
        BOOKED. Used as an alternative concurrency strategy for the
        assignment; the production path uses the pessimistic lock instead.
        """
        stmt = (
            update(Slot)
            .where(
                Slot.id == slot_id,
                Slot.status == SlotStatus.AVAILABLE,
            )
            .values(
                status=SlotStatus.BOOKED,
            )
        )

        result = await self.session.execute(stmt)

        return (result.rowcount or 0) > 0

    async def exists_confirmed_for_slot(
        self,
        slot_id: UUID,
    ) -> bool:
        stmt = (
            select(Booking.id)
            .where(
                Booking.slot_id == slot_id,
                Booking.status == BookingStatus.CONFIRMED,
            )
            .limit(1)
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none() is not None
