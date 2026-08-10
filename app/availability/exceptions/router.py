from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Response,
    status,
)

from app.api.deps import get_availability_exception_service
from app.availability.exceptions.schema import (
    AvailabilityExceptionResponse,
    CreateAvailabilityExceptionRequest,
    UpdateAvailabilityExceptionRequest,
)
from app.availability.exceptions.service import AvailabilityExceptionService

router = APIRouter(
    prefix="/availability/exceptions",
    tags=["Availability Exceptions"],
)


def get_host_id(
    x_user_id: UUID = Header(
        alias="x-user-id",
    ),
) -> UUID:
    return x_user_id


@router.post(
    "",
    response_model=AvailabilityExceptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_availability_exception(
    request: CreateAvailabilityExceptionRequest,
    host_id: UUID = Depends(
        get_host_id,
    ),
    service: AvailabilityExceptionService = Depends(
        get_availability_exception_service,
    ),
):

    exception = await service.create_exception(
        host_id,
        request,
    )

    return AvailabilityExceptionResponse.model_validate(
        exception,
    )


@router.get(
    "",
    response_model=list[AvailabilityExceptionResponse],
)
async def list_availability_exceptions(
    host_id: UUID = Depends(
        get_host_id,
    ),
    service: AvailabilityExceptionService = Depends(
        get_availability_exception_service,
    ),
):

    exceptions = await service.list_exceptions(
        host_id,
    )

    return [
        AvailabilityExceptionResponse.model_validate(
            exception,
        )
        for exception in exceptions
    ]


@router.get(
    "/{exception_id}",
    response_model=AvailabilityExceptionResponse,
)
async def get_availability_exception(
    exception_id: UUID,
    service: AvailabilityExceptionService = Depends(
        get_availability_exception_service,
    ),
):

    exception = await service.get_exception(
        exception_id,
    )

    return AvailabilityExceptionResponse.model_validate(
        exception,
    )


@router.patch(
    "/{exception_id}",
    response_model=AvailabilityExceptionResponse,
)
async def update_availability_exception(
    exception_id: UUID,
    request: UpdateAvailabilityExceptionRequest,
    service: AvailabilityExceptionService = Depends(
        get_availability_exception_service,
    ),
):

    exception = await service.update_exception(
        exception_id,
        request,
    )

    return AvailabilityExceptionResponse.model_validate(
        exception,
    )


@router.delete(
    "/{exception_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_availability_exception(
    exception_id: UUID,
    service: AvailabilityExceptionService = Depends(
        get_availability_exception_service,
    ),
):

    await service.delete_exception(
        exception_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
