from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session

DBSession = Annotated[AsyncSession, Depends(get_session)]

from app.users.repository import UserRepository
from app.users.service import UserService
from app.event_types.repository import EventTypeRepository
from app.event_types.service import EventTypeService
#  user crud
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

#  event type crud
def get_event_type_repository(
    session: DBSession,
) -> EventTypeRepository:
    return EventTypeRepository(
        session,
    )


def get_event_type_service(
    repository: EventTypeRepository = Depends(
        get_event_type_repository,
    ),
) -> EventTypeService:
    return EventTypeService(
        repository,
    )