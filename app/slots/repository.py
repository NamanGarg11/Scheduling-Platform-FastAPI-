from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
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

    async def find_available_for_event_type_in_range(
        self,
        *,
        event_type_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Slot]:
        """AVAILABLE slots for one event type with ``start_at`` in
        ``[start_at, end_at)`` (UTC), ordered by ``start_at`` (S3).

        Served by the existing unique index
        ``uq_slot_event_type_start_end (event_type_id, start_at, end_at)``.
        """

        stmt = (
            select(Slot)
            .where(
                Slot.event_type_id == event_type_id,
                Slot.status == SlotStatus.AVAILABLE,
                Slot.start_at >= start_at,
                Slot.start_at < end_at,
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

    async def find_by_host_starting_in_range(
        self,
        *,
        host_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Slot]:
        """Slots whose ``start_at`` falls in ``[start_at, end_at)`` (UTC).

        The reconciliation boundary for regeneration (ADR-021): only slots
        starting inside the resolved UTC range participate.
        """

        stmt = (
            select(Slot)
            .where(
                Slot.host_id == host_id,
                Slot.start_at >= start_at,
                Slot.start_at < end_at,
            )
            .order_by(
                Slot.start_at.asc(),
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def find_booked_by_host_in_range(
        self,
        *,
        host_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Slot]:
        """BOOKED slots whose ``start_at`` falls in ``[start_at, end_at)`` (UTC)."""

        stmt = (
            select(Slot)
            .where(
                Slot.host_id == host_id,
                Slot.status == SlotStatus.BOOKED,
                Slot.start_at >= start_at,
                Slot.start_at < end_at,
            )
            .order_by(
                Slot.start_at.asc(),
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def insert_many_on_conflict_do_nothing(
        self,
        slots: list[Slot],
    ) -> int:
        """Bulk-insert slots as AVAILABLE, skipping rows that already exist.

        Uses ``ON CONFLICT DO NOTHING`` keyed on the unique constraint
        ``(event_type_id, start_at, end_at)`` (ADR-012). Returns the number of
        rows actually inserted.
        """

        if not slots:
            return 0

        stmt = (
            insert(Slot)
            .values(
                [
                    {
                        "host_id": slot.host_id,
                        "event_type_id": slot.event_type_id,
                        "start_at": slot.start_at,
                        "end_at": slot.end_at,
                        "status": SlotStatus.AVAILABLE,
                    }
                    for slot in slots
                ]
            )
            .on_conflict_do_nothing(
                index_elements=[
                    "event_type_id",
                    "start_at",
                    "end_at",
                ],
            )
        )

        result = await self.session.execute(stmt)

        return int(result.rowcount or 0)

    async def set_status_conditional(
        self,
        slot_ids: list[UUID],
        status: SlotStatus,
    ) -> int:
        """Conditional status update (ADR-011): never overwrites BOOKED.

        ``UPDATE ... WHERE id IN (...) AND status IN ('AVAILABLE','BLOCKED')``.
        A slot that became BOOKED between regeneration's read and this write
        matches zero rows. Returns the number of rows updated.
        """

        if not slot_ids:
            return 0

        stmt = (
            update(Slot)
            .where(
                Slot.id.in_(slot_ids),
                Slot.status.in_(
                    [
                        SlotStatus.AVAILABLE,
                        SlotStatus.BLOCKED,
                    ]
                ),
            )
            .values(
                status=status,
            )
        )

        result = await self.session.execute(stmt)

        return int(result.rowcount or 0)

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
