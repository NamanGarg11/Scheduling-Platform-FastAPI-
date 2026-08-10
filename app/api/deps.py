from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session

DBSession = Annotated[AsyncSession, Depends(get_session)]

from app.availability.exceptions.repository import AvailabilityExceptionRepository
from app.availability.exceptions.service import AvailabilityExceptionService
from app.availability.repository import AvailabilityRepository
from app.availability.service import AvailabilityService
from app.bookings.repository import BookingRepository
from app.bookings.service import BookingService
from app.event_types.repository import EventTypeRepository
from app.event_types.service import EventTypeService
from app.slots.repository import SlotRepository
from app.slots.service import SlotService
from app.slots.slot_generation import SlotGenerationEngine
from app.users.repository import UserRepository
from app.users.service import UserService


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
    user_repository: UserRepository = Depends(
        get_user_repository,
    ),
) -> EventTypeService:
    return EventTypeService(
        repository,
        user_repository,
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
    user_repository: UserRepository = Depends(
        get_user_repository,
    ),
) -> AvailabilityService:
    """
    Create AvailabilityService dependency.
    """

    return AvailabilityService(
        repository,
        user_repository,
    )
# availability exceptions crud
# repository dependency
def get_availability_exception_repository(
    session: DBSession,
) -> AvailabilityExceptionRepository:
    """
    Create AvailabilityExceptionRepository dependency.
    """

    return AvailabilityExceptionRepository(
        session,
    )
# service dependency
def get_availability_exception_service(
    repository: AvailabilityExceptionRepository = Depends(
        get_availability_exception_repository,
    ),
    user_repository: UserRepository = Depends(
        get_user_repository,
    ),
) -> AvailabilityExceptionService:
    """
    Create AvailabilityExceptionService dependency.
    """

    return AvailabilityExceptionService(
        repository,
        user_repository,
    )

# slot crud
# repository dependency
def get_slot_repository(
    session: DBSession,
) -> SlotRepository:
    return SlotRepository(session)
def get_slot_generation_engine() -> SlotGenerationEngine:
    return SlotGenerationEngine()
# service dependency
def get_slot_service(
    slot_repository: SlotRepository = Depends(
        get_slot_repository,
    ),
    event_type_repository: EventTypeRepository = Depends(
        get_event_type_repository,
    ),
    availability_repository: AvailabilityRepository = Depends(
        get_availability_repository,
    ),
    availability_exception_repository: AvailabilityExceptionRepository = Depends(
        get_availability_exception_repository,
    ),
    user_repository: UserRepository = Depends(
        get_user_repository,
    ),
    generation_engine: SlotGenerationEngine = Depends(
        get_slot_generation_engine,
    ),
) -> SlotService:

    return SlotService(
        slot_repository=slot_repository,
        event_type_repository=event_type_repository,
        availability_repository=availability_repository,
        availability_exception_repository=availability_exception_repository,
        user_repository=user_repository,
        generation_engine=generation_engine,
    )

# booking engine 
# repository dependency
def get_booking_repository(
    session: DBSession,
) -> BookingRepository:
    return BookingRepository(session)
# service dependency
def get_booking_service(
    repository: BookingRepository = Depends(
        get_booking_repository,
    ),
    user_repository: UserRepository = Depends(
        get_user_repository,
    ),
) -> BookingService:

    return BookingService(
        repository=repository,
        user_repository=user_repository,
    )
