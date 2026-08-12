from datetime import date, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability.exceptions.enums import AvailabilityExceptionKind
from app.availability.exceptions.model import AvailabilityException
from app.core.database.repository import BaseRepository


class AvailabilityExceptionRepository(
    BaseRepository[AvailabilityException],
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(
            session,
            AvailabilityException,
        )

    async def find_for_host_and_range(
        self,
        host_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[AvailabilityException]:
        """All exceptions affecting ``host_id`` between two inclusive dates."""
        stmt = (
            select(AvailabilityException)
            .where(
                AvailabilityException.host_id == host_id,
                AvailabilityException.exception_date >= start_date,
                AvailabilityException.exception_date <= end_date,
            )
            .order_by(
                AvailabilityException.exception_date,
                AvailabilityException.start_time,
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def find_all_for_host(
        self,
        host_id: UUID,
    ) -> list[AvailabilityException]:
        stmt = (
            select(AvailabilityException)
            .where(
                AvailabilityException.host_id == host_id,
            )
            .order_by(
                AvailabilityException.exception_date,
                AvailabilityException.start_time,
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def exists_for_host(
        self,
        host_id: UUID,
        kind: AvailabilityExceptionKind,
        exception_date: date,
        start_time: time | None,
        end_time: time | None,
    ) -> bool:
        return await self.exists(
            filters=[
                AvailabilityException.host_id == host_id,
                AvailabilityException.kind == kind,
                AvailabilityException.exception_date == exception_date,
                AvailabilityException.start_time == start_time,
                AvailabilityException.end_time == end_time,
            ]
        )

    async def exists_for_host_excluding(
        self,
        host_id: UUID,
        kind: AvailabilityExceptionKind,
        exception_date: date,
        start_time: time | None,
        end_time: time | None,
        exclude_id: UUID,
    ) -> bool:
        stmt = (
            select(AvailabilityException.id)
            .where(
                AvailabilityException.host_id == host_id,
                AvailabilityException.kind == kind,
                AvailabilityException.exception_date == exception_date,
                AvailabilityException.start_time == start_time,
                AvailabilityException.end_time == end_time,
                AvailabilityException.id != exclude_id,
            )
            .limit(1)
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none() is not None
