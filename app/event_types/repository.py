from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.repository import BaseRepository, ModelT
from app.event_types.model import EventType

class EventTypeRepository(
    BaseRepository[EventType],
):

    def __init__(
        self,
        session: AsyncSession,
    ):
        super().__init__(
            session,
            EventType,
        )

    async def find_by_slug(
        self,
        slug: str,
    ) -> EventType | None:

        stmt = (
            select(EventType)
            .where(EventType.slug == slug)
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def find_by_host_and_slug(
        self,
        host_id: UUID,
        slug: str,
    ) -> EventType | None:

        stmt = (
            select(EventType)
            .where(
                EventType.host_id == host_id,
                EventType.slug == slug,
            )
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def list_by_host(
        self,
        host_id: UUID,
    ) -> list[EventType]:

        stmt = (
            select(EventType)
            .where(
                EventType.host_id == host_id
            )
            .order_by(
                EventType.created_at.desc()
            )
        )

        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def slug_exists(
        self,
        host_id: UUID,
        slug: str,
    ) -> bool:
        return await self.exists(
            filters=[
                EventType.host_id == host_id,
                EventType.slug == slug,
            ]
        )