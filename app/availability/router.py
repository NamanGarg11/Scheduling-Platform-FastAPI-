from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Response,
    status,
)

from app.api.deps import (
    get_availability_service,
)
from app.availability.schema import (
    AvailabilityResponse,
    CreateAvailabilityRequest,
    UpdateAvailabilityRequest,
)
from app.availability.service import AvailabilityService

router = APIRouter(
    prefix="/availability",
    tags=["Availability"],
)
def get_host_id(
    x_user_id: UUID = Header(
        alias="x-user-id",
    ),
) -> UUID:
    return x_user_id
@router.post(
    "",
    response_model=AvailabilityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_availability(
    request: CreateAvailabilityRequest,
    host_id: UUID = Depends(
        get_host_id,
    ),
    service: AvailabilityService = Depends(
        get_availability_service,
    ),
):

    availability = await service.create_availability(
        host_id,
        request,
    )

    return AvailabilityResponse.model_validate(
        availability,
    )
@router.get(
    "",
    response_model=list[AvailabilityResponse],
)
async def get_week_schedule(
    host_id: UUID = Depends(
        get_host_id,
    ),
    service: AvailabilityService = Depends(
        get_availability_service,
    ),
):

    schedule = await service.get_week_schedule(
        host_id,
    )

    return [
        AvailabilityResponse.model_validate(
            availability,
        )
        for availability in schedule
    ]
@router.get(
    "/{availability_id}",
    response_model=AvailabilityResponse,
)
async def get_availability(
    availability_id: UUID,
    service: AvailabilityService = Depends(
        get_availability_service,
    ),
):

    availability = await service.get_availability(
        availability_id,
    )

    return AvailabilityResponse.model_validate(
        availability,
    )
@router.patch(
    "/{availability_id}",
    response_model=AvailabilityResponse,
)
async def update_availability(
    availability_id: UUID,
    request: UpdateAvailabilityRequest,
    service: AvailabilityService = Depends(
        get_availability_service,
    ),
):

    availability = await service.update_availability(
        availability_id,
        request,
    )

    return AvailabilityResponse.model_validate(
        availability,
    )
@router.delete(
    "/{availability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_availability(
    availability_id: UUID,
    service: AvailabilityService = Depends(
        get_availability_service,
    ),
):

    await service.delete_availability(
        availability_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
