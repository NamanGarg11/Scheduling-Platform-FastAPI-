from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import get_slot_service
from app.slots.schema import (
    GenerateSlotsRequest,
    SlotGenerationResponse,
)
from app.slots.service import SlotService


router = APIRouter(
    prefix="/api/v1/slots",
    tags=["Slots"],
)


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