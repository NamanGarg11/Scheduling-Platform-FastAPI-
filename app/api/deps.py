from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session

DBSession = Annotated[AsyncSession, Depends(get_session)]

from app.users.repository import UserRepository
from app.users.service import UserService
from app.event_types.repository import EventTypeRepository
from app.event_types.service import EventTypeService
from app.availability.repository import AvailabilityRepository
from app.availability.service import AvailabilityService
#  user crud
# repository dependency
def get_user_repository(
    session: DBSession,
)-> UserRepository:
    return UserRepository(session)
# service dependency
def get_user_service(
    repository: UserRepository = Depends(
        get_user_repository
    ),
)-> UserService:
    return UserService(repository)

#  event type crud
#repository dependency
def get_event_type_repository(
    session: DBSession,
) -> EventTypeRepository:
    return EventTypeRepository(
        session,
    )
# service dependency
def get_event_type_service(
    repository: EventTypeRepository = Depends(
        get_event_type_repository,
    ),
) -> EventTypeService:
    return EventTypeService(
        repository,
    )

# availability crud
# repository dependency
def get_availability_repository(
    session: DBSession,
) -> AvailabilityRepository:
    """
    Create AvailabilityRepository dependency.
    """

    return AvailabilityRepository(
        session,
    )
# service dependency
def get_availability_service(
    repository: AvailabilityRepository = Depends(
        get_availability_repository,
    ),
) -> AvailabilityService:
    """
    Create AvailabilityService dependency.
    """

    return AvailabilityService(
        repository,
    )