from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.repository import BaseRepository
from app.users.model import User


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def find_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_slug(self, slug: str) -> User | None:
        stmt = select(User).where(User.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()