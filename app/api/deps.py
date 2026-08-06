from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session

DBSession = Annotated[AsyncSession, Depends(get_session)]

from app.users.repository import UserRepository
from app.users.service import UserService


def get_user_repository(
    session: DBSession,
)-> UserRepository:
    return UserRepository(session)


def get_user_service(
    repository: UserRepository = Depends(
        get_user_repository
    ),
)-> UserService:
    return UserService(repository)