"""Public slot listing service (S3, ADR-017).

Strictly a **read-only projection** of persisted slot availability:

- no slot generation (S1 owns the mathematics)
- no regeneration/reconciliation (S2 owns that)
- no reservation, booking, or mutation of any kind

It resolves the user/event type, validates the request range, converts the
host/requested-local date boundaries to UTC, queries only AVAILABLE persisted
slots, filters past ones, and groups the result by local calendar day while the
returned timestamps stay UTC instants.
"""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.exceptions.base import (
    NotFoundException,
    ValidationException,
)
from app.core.logging import get_logger
from app.event_types.repository import EventTypeRepository
from app.slots.repository import SlotRepository
from app.slots.schema import (
    PublicDayGroup,
    PublicEventTypeSummary,
    PublicSlotListingResponse,
    PublicSlotResponse,
)
from app.slots.service import SLOT_GENERATION_DAYS
from app.users.repository import UserRepository

logger = get_logger(__name__)

# Hard maximum for the public listing range (ADR-017).
MAX_PUBLIC_RANGE_DAYS = 62


class PublicSlotService:

    def __init__(
        self,
        slot_repository: SlotRepository,
        event_type_repository: EventTypeRepository,
        user_repository: UserRepository,
    ) -> None:
        self.slot_repository = slot_repository
        self.event_type_repository = event_type_repository
        self.user_repository = user_repository

    async def list_public_slots(
        self,
        user_id: UUID,
        slug: str,
        from_date: date | None = None,
        to_date: date | None = None,
        requested_timezone: str | None = None,
    ) -> PublicSlotListingResponse:

        # 1. Resolve the user (404 if missing).
        user = await self.user_repository.find_by_id(
            user_id,
        )

        if user is None:
            logger.warning(
                "Public listing requested for unknown user %s.",
                user_id,
            )

            raise NotFoundException(
                "User not found.",
            )

        # 2. Resolve the event type, scoped to the user (slug alone is not
        #    trusted — an event type belonging to another user is not exposed).
        event_type = (
            await self.event_type_repository.find_by_host_and_slug(
                user_id,
                slug,
            )
        )

        if event_type is None or not event_type.is_active:
            logger.warning(
                "Public listing requested for unknown/inactive event type "
                "%s of user %s.",
                slug,
                user_id,
            )

            raise NotFoundException(
                "Event type not found.",
            )

        # 3. Resolve the grouping timezone (requested, else the host's).
        tz_name = requested_timezone or user.timezone

        try:
            tz = ZoneInfo(tz_name)
        except (KeyError, ValueError):
            logger.warning(
                "Public listing requested with invalid timezone %r.",
                tz_name,
            )

            raise ValidationException(
                "Invalid timezone.",
            )

        # 4. Resolve the default range (host calendar time, like S2).
        local_today = datetime.now(tz).date()
        from_local = from_date or local_today
        to_local = to_date or (
            from_local + timedelta(days=SLOT_GENERATION_DAYS - 1)
        )

        # 5. Validate the range.
        if from_local > to_local:
            raise ValidationException(
                "from_date cannot be after to_date.",
            )

        if (to_local - from_local).days > MAX_PUBLIC_RANGE_DAYS:
            raise ValidationException(
                f"Requested range exceeds the {MAX_PUBLIC_RANGE_DAYS}-day "
                "maximum.",
            )

        # 6. Convert the local date boundaries to UTC for the persistence query.
        range_start_utc = datetime.combine(
            from_local,
            time.min,
            tzinfo=tz,
        ).astimezone(timezone.utc)

        range_end_utc = datetime.combine(
            to_local + timedelta(days=1),
            time.min,
            tzinfo=tz,
        ).astimezone(timezone.utc)

        # 7. Query persisted AVAILABLE slots (read-only; no generation).
        slots = await self.slot_repository.find_available_for_event_type_in_range(
            event_type_id=event_type.id,
            start_at=range_start_utc,
            end_at=range_end_utc,
        )

        # 8. Exclude past slots (a slot starting now-or-earlier is not bookable).
        now_utc = datetime.now(timezone.utc)
        slots = [
            slot
            for slot in slots
            if slot.start_at > now_utc
        ]

        # 9. Group by local calendar day in the requested timezone, keeping
        #    the timestamps as UTC instants.
        groups: dict[date, list[PublicSlotResponse]] = {}

        for slot in slots:
            local_day = slot.start_at.astimezone(tz).date()

            groups.setdefault(
                local_day,
                [],
            ).append(
                PublicSlotResponse(
                    start_at=slot.start_at,
                    end_at=slot.end_at,
                )
            )

        days = [
            PublicDayGroup(
                date=day,
                slots=groups[day],
            )
            for day in sorted(groups)
        ]

        return PublicSlotListingResponse(
            event_type=PublicEventTypeSummary(
                id=event_type.id,
                slug=event_type.slug,
                title=event_type.title,
            ),
            timezone=tz_name,
            days=days,
        )
