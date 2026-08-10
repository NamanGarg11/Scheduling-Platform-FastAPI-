from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from app.api.deps import get_slot_service
from app.slots.schema import (
    GenerateSlotsRequest,
    RegenerateSlotsRequest,
    SlotGenerationResponse,
    SlotRegenerationResponse,
)
from app.slots.service import SlotService

router = APIRouter(
    prefix="/api/v1/slots",
    tags=["Slots"],
)


def get_host_id(
    x_user_id: UUID = Header(
        alias="x-user-id",
    ),
) -> UUID:
    return x_user_id


@router.post(
    "/generate",
    response_model=SlotGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_slots(
    request: GenerateSlotsRequest,
    service: SlotService = Depends(
        get_slot_service,
    ),
) -> SlotGenerationResponse:

    return await service.generate_slots(
        request,
    )


@router.post(
    "/regenerate",
    response_model=SlotRegenerationResponse,
)
async def regenerate_slots(
    request: RegenerateSlotsRequest,
    host_id: UUID = Depends(
        get_host_id,
    ),
    service: SlotService = Depends(
        get_slot_service,
    ),
) -> SlotRegenerationResponse:

    return await service.regenerate_host_slots(
        host_id,
        request.from_date,
        request.to_date,
    )