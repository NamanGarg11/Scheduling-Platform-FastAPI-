from uuid import UUID

from app.availability.enums import DayOfWeek
from app.availability.model import Availability
from app.availability.repository import AvailabilityRepository
from app.availability.schema import (
    CreateAvailabilityRequest,
    UpdateAvailabilityRequest,
)
from app.core.exceptions.base import (
    ConflictException,
    NotFoundException,
)
from app.core.logging import get_logger
from app.users.repository import UserRepository

logger = get_logger(__name__)
class AvailabilityService:

    def __init__(
        self,
        repository: AvailabilityRepository,
        user_repository: UserRepository,
    ):
        self.repository = repository
        self.user_repository = user_repository
        # centralized place to handle all the business logic related to availability
    async def _validate_duplicate_day(
        self,
        host_id: UUID,
        day: DayOfWeek,
    ) -> None:

        if await self.repository.exists_for_day(
            host_id,
            day,
        ):
            raise ConflictException(
                f"Availability already exists for {day.value}."
            )
        # find availability by id and host id
    async def _get_or_raise(
        self,
        availability_id: UUID,
    ) -> Availability:

        availability = await self.repository.find_by_id(
            availability_id,
        )

        if availability is None:

            logger.warning(
                "Availability %s not found.",
                availability_id,
            )

            raise NotFoundException(
                "Availability not found."
            )

        return availability
    # create availability
    async def create_availability(
        self,
        host_id: UUID,
        request: CreateAvailabilityRequest,
    ) -> Availability:

        logger.info(
            "Creating availability for host %s on %s.",
            host_id,
            request.day_of_week.value,
        )

        host = await self.user_repository.find_by_id(
            host_id,
        )

        if host is None:
            logger.warning(
                "Host %s does not exist. Rejecting availability creation.",
                host_id,
            )

            raise NotFoundException(
                "Availability host not found."
            )

        await self._validate_duplicate_day(
            host_id,
            request.day_of_week,
        )

        availability = Availability(
            host_id=host_id,
            day_of_week=request.day_of_week,
            start_time=request.start_time,
            end_time=request.end_time,
            is_available=request.is_available,
        )

        saved = await self.repository.save(
            availability,
        )

        logger.info(
            "Availability %s created.",
            saved.id,
        )

        return saved
    # get availability by id
    async def get_availability(
        self,
        availability_id: UUID,
    ) -> Availability:

        return await self._get_or_raise(
            availability_id,
        )
    # get weekly schedule by host id
    async def get_week_schedule(
        self,
        host_id: UUID,
    ) -> list[Availability]:

        logger.info(
            "Fetching weekly schedule for host %s.",
            host_id,
        )

        return await self.repository.find_week_schedule(
            host_id,
        )
    # update availability by id
    async def update_availability(
        self,
        availability_id: UUID,
        request: UpdateAvailabilityRequest,
    ) -> Availability:

        logger.info(
            "Updating availability %s.",
            availability_id,
        )

        availability = await self._get_or_raise(
            availability_id,
        )

        updates = request.model_dump(
            exclude_unset=True,
        )
        new_day = updates.get("day_of_week")
        if (
            new_day is not None
            and new_day != availability.day_of_week
        ):
            await self._validate_duplicate_day(
                availability.host_id,
                new_day,
            )
        for field, value in updates.items():
            setattr(
                availability,
                field,
                value,
            )

        updated = await self.repository.save(
            availability,
        )

        logger.info(
            "Availability %s updated successfully.",
            updated.id,
        )

        return updated
    # delete availability by id
    async def delete_availability(
        self,
        availability_id: UUID,
    ) -> None:

        logger.info(
            "Deleting availability %s.",
            availability_id,
        )

        availability = await self._get_or_raise(
            availability_id,
        )

        await self.repository.delete(
            availability,
        )

        logger.info(
            "Availability %s deleted.",
            availability_id,
        )
    