from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.repository import BaseRepository
from app.slots.enums import SlotStatus
from app.slots.model import Slot


class SlotRepository(BaseRepository[Slot]):

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(
            session,
            Slot,
        )

    async def find_in_range(
        self,
        *,
        host_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Slot]:

        stmt = (
            select(Slot)
            .where(
                Slot.host_id == host_id,
                Slot.start_at < end_at,
                Slot.end_at > start_at,
            )
            .order_by(
                Slot.start_at.asc(),
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def find_available_in_range(
        self,
        *,
        host_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Slot]:

        stmt = (
            select(Slot)
            .where(
                Slot.host_id == host_id,
                Slot.status == SlotStatus.AVAILABLE,
                Slot.start_at < end_at,
                Slot.end_at > start_at,
            )
            .order_by(
                Slot.start_at.asc(),
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def find_by_event_type_and_start(
        self,
        *,
        event_type_id: UUID,
        start_at: datetime,
    ) -> Slot | None:

        stmt = (
            select(Slot)
            .where(
                Slot.event_type_id == event_type_id,
                Slot.start_at == start_at,
            )
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def find_by_event_type_in_range(
        self,
        *,
        event_type_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Slot]:

        stmt = (
            select(Slot)
            .where(
                Slot.event_type_id == event_type_id,
                Slot.start_at < end_at,
                Slot.end_at > start_at,
            )
            .order_by(
                Slot.start_at.asc(),
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def update_status(
        self,
        *,
        slot: Slot,
        status: SlotStatus,
    ) -> Slot:

        slot.status = status

        return await self.save(slot)
    async def save_many(
        self,
        slots: list[Slot],
    ) -> list[Slot]:

        if not slots:
            return []

        self.session.add_all(slots)

        await self.session.flush()

        for slot in slots:
            await self.session.refresh(slot)

        return slots
