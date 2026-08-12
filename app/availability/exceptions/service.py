from datetime import date, time
from uuid import UUID

from app.availability.exceptions.enums import AvailabilityExceptionKind
from app.availability.exceptions.model import AvailabilityException
from app.availability.exceptions.repository import AvailabilityExceptionRepository
from app.availability.exceptions.schema import (
    CreateAvailabilityExceptionRequest,
    UpdateAvailabilityExceptionRequest,
)
from app.core.exceptions.base import (
    ConflictException,
    NotFoundException,
)
from app.core.logging import get_logger
from app.users.repository import UserRepository

logger = get_logger(__name__)


class AvailabilityExceptionService:

    def __init__(
        self,
        repository: AvailabilityExceptionRepository,
        user_repository: UserRepository,
    ) -> None:
        self.repository = repository
        self.user_repository = user_repository

    async def _validate_host(
        self,
        host_id: UUID,
    ) -> None:
        host = await self.user_repository.find_by_id(
            host_id,
        )

        if host is None:
            logger.warning(
                "Host %s does not exist. Rejecting exception operation.",
                host_id,
            )

            raise NotFoundException(
                "Availability exception host not found."
            )

    async def _get_or_raise(
        self,
        exception_id: UUID,
    ) -> AvailabilityException:

        exception = await self.repository.find_by_id(
            exception_id,
        )

        if exception is None:

            logger.warning(
                "Availability exception %s not found.",
                exception_id,
            )

            raise NotFoundException(
                "Availability exception not found."
            )

        return exception

    async def _validate_duplicate(
        self,
        host_id: UUID,
        kind: AvailabilityExceptionKind,
        exception_date: date,
        start_time: time | None,
        end_time: time | None,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        if exclude_id is not None:
            exists = await self.repository.exists_for_host_excluding(
                host_id,
                kind,
                exception_date,
                start_time,
                end_time,
                exclude_id,
            )
        else:
            exists = await self.repository.exists_for_host(
                host_id,
                kind,
                exception_date,
                start_time,
                end_time,
            )

        if exists:
            raise ConflictException(
                f"Availability exception already exists for "
                f"{exception_date} ({kind.value})."
            )

    async def create_exception(
        self,
        host_id: UUID,
        request: CreateAvailabilityExceptionRequest,
    ) -> AvailabilityException:

        logger.info(
            "Creating availability exception for host %s on %s (%s).",
            host_id,
            request.exception_date,
            request.kind.value,
        )

        await self._validate_host(
            host_id,
        )

        await self._validate_duplicate(
            host_id,
            request.kind,
            request.exception_date,
            request.start_time,
            request.end_time,
        )

        exception = AvailabilityException(
            host_id=host_id,
            exception_date=request.exception_date,
            kind=request.kind,
            start_time=request.start_time,
            end_time=request.end_time,
        )

        saved = await self.repository.save(
            exception,
        )

        logger.info(
            "Availability exception %s created.",
            saved.id,
        )

        return saved

    async def list_exceptions(
        self,
        host_id: UUID,
    ) -> list[AvailabilityException]:

        logger.info(
            "Fetching availability exceptions for host %s.",
            host_id,
        )

        return await self.repository.find_all_for_host(
            host_id,
        )

    async def get_exception(
        self,
        exception_id: UUID,
    ) -> AvailabilityException:

        return await self._get_or_raise(
            exception_id,
        )

    async def update_exception(
        self,
        exception_id: UUID,
        request: UpdateAvailabilityExceptionRequest,
    ) -> AvailabilityException:

        logger.info(
            "Updating availability exception %s.",
            exception_id,
        )

        exception = await self._get_or_raise(
            exception_id,
        )

        updates = request.model_dump(
            exclude_unset=True,
        )

        new_kind = updates.get("kind", exception.kind)
        new_date = updates.get("exception_date", exception.exception_date)
        new_start = updates.get("start_time", exception.start_time)
        new_end = updates.get("end_time", exception.end_time)

        if (
            new_kind != exception.kind
            or new_date != exception.exception_date
            or new_start != exception.start_time
            or new_end != exception.end_time
        ):
            await self._validate_duplicate(
                exception.host_id,
                new_kind,
                new_date,
                new_start,
                new_end,
                exclude_id=exception.id,
            )

        for field, value in updates.items():
            setattr(
                exception,
                field,
                value,
            )

        updated = await self.repository.save(
            exception,
        )

        logger.info(
            "Availability exception %s updated successfully.",
            updated.id,
        )

        return updated

    async def delete_exception(
        self,
        exception_id: UUID,
    ) -> None:

        logger.info(
            "Deleting availability exception %s.",
            exception_id,
        )

        exception = await self._get_or_raise(
            exception_id,
        )

        await self.repository.delete(
            exception,
        )

        logger.info(
            "Availability exception %s deleted.",
            exception_id,
        )
