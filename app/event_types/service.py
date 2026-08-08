from uuid import UUID

from app.core.logging import get_logger

logger = get_logger(__name__)

from app.core.exceptions.base import NotFoundException, ValidationException
from app.event_types.model import EventType
from app.event_types.repository import EventTypeRepository
from app.event_types.schema import (
    CreateEventTypeRequest,
    UpdateEventTypeRequest,
)
from app.users.repository import UserRepository
from app.utils.slug import slugify

class EventTypeService:

# ''' dependency injection for the EventTypeRepository using the constructor '''

    def __init__(
        self,
        repository: EventTypeRepository,
        user_repository: UserRepository,
    ):
        self.repository = repository
        self.user_repository = user_repository
#  method to generate a unique slug for an event type based on the title and host ID
    async def generate_unique_slug(
        self,
        host_id: UUID,
        title: str,
    ) -> str:
        """
        Generate a unique slug for an event type.
        """

        base_slug = slugify(title)
        slug = base_slug
        counter = 2

        while await self.repository.slug_exists(
            host_id,
            slug,
        ):
            logger.debug(
                "Slug '%s' already exists for host %s. Trying another.",
                slug,
                host_id,
            )

            slug = f"{base_slug}-{counter}"
            counter += 1

        return slug

    #  method to create an event type using the request dto in the schema.py
    async def create_event_type(
        self,
        host_id: UUID,
        request: CreateEventTypeRequest,
    ) -> EventType:
        """
        Create a new event type.
        """

        logger.info(
            "Creating event type '%s' for host %s.",
            request.title,
            host_id,
        )

        #
        # Business Validation
        #

        host = await self.user_repository.find_by_id(
            host_id,
        )

        if host is None:
            logger.warning(
                "Host %s does not exist. Rejecting event type creation.",
                host_id,
            )

            raise NotFoundException(
                "Event type host not found."
            )

        if (
            request.location_type.name == "IN_PERSON"
            and not request.location_value
        ):
            raise ValidationException(
                "Location is required for in-person meetings."
            )

        slug = await self.generate_unique_slug(
            host_id,
            request.title,
        )

        event_type = EventType(
            host_id=host_id,
            title=request.title,
            description=request.description,
            slug=slug,
            duration_minutes=request.duration_minutes,
            location_type=request.location_type,
            location_value=request.location_value,
            buffer_before_minutes=request.buffer_before_minutes,
            buffer_after_minutes=request.buffer_after_minutes,
        )

        saved_event = await self.repository.save(
            event_type,
        )

        logger.info(
            "Created event type %s successfully.",
            saved_event.id,
        )

        return saved_event
    # method to get event by id using the repository and raise an exception if not found
    async def get_event_type(
        self,
        event_type_id: UUID,
    ) -> EventType:
        """
        Fetch an event type by id.
        """

        event_type = await self.repository.find_by_id(
            event_type_id,
        )

        if event_type is None:

            logger.warning(
                "Event type %s not found.",
                event_type_id,
            )

            raise NotFoundException(
                "Event type not found."
            )

        return event_type
    # method to list all the event types for a given host Id using the repository
    async def list_event_types(
        self,
        host_id: UUID,
        ) -> list[EventType]:
        """
        Return all event types for a host.
        """

        logger.debug(
            "Fetching event types for host %s.",
            host_id,
        )

        return await self.repository.list_by_host(
            host_id,
        )
    # method to update an event type using the request dto in the schema.py and raise an exception if not found
    async def update_event_type(
        self,
        event_type_id: UUID,
        request: UpdateEventTypeRequest,
    ) -> EventType:
        """
        Update an existing event type.
        """

        logger.info(
            "Updating event type %s.",
            event_type_id,
        )

        event_type = await self.get_event_type(
            event_type_id,
        )

        updates = request.model_dump(
            exclude_unset=True,
        )

        #
        # Business Validation
        #

        if (
            updates.get("location_type") is not None
            and updates["location_type"].name == "IN_PERSON"
            and not updates.get("location_value")
        ):
            raise ValidationException(
                "Location is required for in-person meetings."
            )

        if "title" in updates:

            event_type.title = updates["title"]

            event_type.slug = await self.generate_unique_slug(
                event_type.host_id,
                updates["title"],
            )

        for field, value in updates.items():

            if field == "title":
                continue

            setattr(
                event_type,
                field,
                value,
            )

        updated_event = await self.repository.save(
            event_type,
        )

        logger.info(
            "Updated event type %s successfully.",
            updated_event.id,
        )

        return updated_event
    # method to delete an event type using the repository and raise an exception if not found 
    async def delete_event_type(
        self,
        event_type_id: UUID,
    ) -> None:
        """
        Delete an event type.
        """

        logger.info(
            "Deleting event type %s.",
            event_type_id,
        )

        event_type = await self.get_event_type(
            event_type_id,
        )

        await self.repository.delete(
            event_type,
        )

        logger.info(
            "Deleted event type %s successfully.",
            event_type_id,
        )