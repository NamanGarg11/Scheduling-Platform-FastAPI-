from datetime import datetime, time, timezone
from uuid import UUID

from app.availability.repository import AvailabilityRepository
from app.core.exceptions.base import NotFoundException
from app.core.logging import get_logger
from app.event_types.repository import EventTypeRepository
from app.slots.model import Slot
from app.slots.repository import SlotRepository
from app.slots.schema import (
    GenerateSlotsRequest,
    SlotGenerationResponse,
)
from app.slots.slot_generation import SlotGenerationEngine
from app.users.repository import UserRepository


logger = get_logger(__name__)


class SlotService:

    def __init__(
        self,
        slot_repository: SlotRepository,
        event_type_repository: EventTypeRepository,
        availability_repository: AvailabilityRepository,
        user_repository: UserRepository,
        generation_engine: SlotGenerationEngine,
    ) -> None:
        self.slot_repository = slot_repository
        self.event_type_repository = event_type_repository
        self.availability_repository = availability_repository
        self.user_repository = user_repository
        self.generation_engine = generation_engine

    async def generate_slots(
        self,
        request: GenerateSlotsRequest,
    ) -> SlotGenerationResponse:

        logger.info(
            "Starting slot generation for event type %s "
            "from %s to %s.",
            request.event_type_id,
            request.start_date,
            request.end_date,
        )

        event_type = await self.event_type_repository.find_by_id(
            request.event_type_id,
        )

        if event_type is None:
            logger.warning(
                "Event type %s not found.",
                request.event_type_id,
            )

            raise NotFoundException(
                "Event type not found.",
            )

        if not event_type.is_active:
            logger.warning(
                "Attempted slot generation for inactive "
                "event type %s.",
                event_type.id,
            )

            return SlotGenerationResponse(
                event_type_id=event_type.id,
                start_date=request.start_date,
                end_date=request.end_date,
                generated_count=0,
                skipped_count=0,
                slots=[],
            )

        host = await self.user_repository.find_by_id(
            event_type.host_id,
        )

        if host is None:
            logger.error(
                "Host %s for event type %s was not found.",
                event_type.host_id,
                event_type.id,
            )

            raise NotFoundException(
                "Event type host not found.",
            )

        availability = (
            await self.availability_repository.find_week_schedule(
                event_type.host_id,
            )
        )

        if not availability:
            logger.info(
                "No availability found for host %s.",
                event_type.host_id,
            )

            return SlotGenerationResponse(
                event_type_id=event_type.id,
                start_date=request.start_date,
                end_date=request.end_date,
                generated_count=0,
                skipped_count=0,
                slots=[],
            )

        candidates = self.generation_engine.generate(
            event_type=event_type,
            availability=availability,
            start_date=request.start_date,
            end_date=request.end_date,
            timezone=host.timezone,
        )

        if not candidates:
            logger.info(
                "No slot candidates generated for event type %s.",
                event_type.id,
            )

            return SlotGenerationResponse(
                event_type_id=event_type.id,
                start_date=request.start_date,
                end_date=request.end_date,
                generated_count=0,
                skipped_count=0,
                slots=[],
            )

        range_start = candidates[0].start_at
        range_end = candidates[-1].end_at

        existing_slots = (
            await self.slot_repository
            .find_by_event_type_in_range(
                event_type_id=event_type.id,
                start_at=range_start,
                end_at=range_end,
            )
        )

        existing_by_start = {
            slot.start_at: slot
            for slot in existing_slots
        }

        new_slots: list[Slot] = []
        skipped_count = 0

        for candidate in candidates:

            if candidate.start_at in existing_by_start:
                skipped_count += 1
                continue

            new_slots.append(
                Slot(
                    host_id=event_type.host_id,
                    event_type_id=event_type.id,
                    start_at=candidate.start_at,
                    end_at=candidate.end_at,
                )
            )

        saved_slots = await self.slot_repository.save_many(
            new_slots,
        )

        logger.info(
            "Slot generation completed for event type %s. "
            "Generated=%s, skipped=%s.",
            event_type.id,
            len(saved_slots),
            skipped_count,
        )

        return SlotGenerationResponse(
            event_type_id=event_type.id,
            start_date=request.start_date,
            end_date=request.end_date,
            generated_count=len(saved_slots),
            skipped_count=skipped_count,
            slots=saved_slots,
        )