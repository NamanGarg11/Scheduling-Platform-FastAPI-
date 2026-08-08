from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability.enums import DayOfWeek
from app.availability.model import Availability
from app.core.database.repository import BaseRepository


class AvailabilityRepository(
    BaseRepository[Availability],
):
    def __init__(
        self,
        session: AsyncSession,
    ):
        super().__init__(
            session,
            Availability,
        )

    async def find_by_day(
        self,
        host_id: UUID,
        day: DayOfWeek,
    ) -> Availability | None:
        stmt = (
            select(Availability)
            .where(
                Availability.host_id == host_id,
                Availability.day_of_week == day,
            )
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def exists_for_day(
        self,
        host_id: UUID,
        day: DayOfWeek,
    ) -> bool:
        return await self.exists(
            filters=[
                Availability.host_id == host_id,
                Availability.day_of_week == day,
            ]
        )

    # find week schedule by host id
    async def find_week_schedule(
        self,
        host_id: UUID,
    ) -> list[Availability]:
        stmt = (
            select(Availability)
            .where(
                Availability.host_id == host_id,
            )
            .order_by(
                Availability.day_of_week,
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def find_active_schedule(
        self,
        host_id: UUID,
    ) -> list[Availability]:
        stmt = (
            select(Availability)
            .where(
                Availability.host_id == host_id,
                Availability.is_available.is_(True),
            )
            .order_by(
                Availability.day_of_week,
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())