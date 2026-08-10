from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_public_slot_service
from app.slots.public_service import PublicSlotService
from app.slots.schema import PublicSlotListingResponse

router = APIRouter(
    prefix="/api/public/users/{user_id}/event-types/{slug}",
    tags=["Public Slots"],
)


@router.get(
    "/slots",
    response_model=PublicSlotListingResponse,
)
async def list_public_slots(
    user_id: UUID,
    slug: str,
    from_date: date | None = Query(
        default=None,
    ),
    to_date: date | None = Query(
        default=None,
    ),
    timezone: str | None = Query(
        default=None,
    ),
    service: PublicSlotService = Depends(
        get_public_slot_service,
    ),
) -> PublicSlotListingResponse:

    return await service.list_public_slots(
        user_id,
        slug,
        from_date,
        to_date,
        requested_timezone=timezone,
    )
