from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import get_event_type_service
from app.event_types.schema import (
    CreateEventTypeRequest,
    EventTypeResponse,
    UpdateEventTypeRequest,
)
from app.event_types.service import EventTypeService
# router init
router = APIRouter(
    prefix="/event-types",
    tags=["Event Types"],
)
# dependency to get the host ID from the request header
def get_host_id(
    x_user_id: UUID = Header(
        alias="x-user-id",
    ),
) -> UUID:
    return x_user_id
# endpoint to create an event type using the request dto in the schema.py
@router.post(
    "",
    response_model=EventTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_event_type(
    request: CreateEventTypeRequest,
    host_id: UUID = Depends(get_host_id),
    service: EventTypeService = Depends(
        get_event_type_service,
    ),
):
    event_type = await service.create_event_type(
        host_id,
        request,
    )

    return EventTypeResponse.model_validate(
        event_type,
    )
# endpoint to get an all event types
@router.get(
    "",
    response_model=list[EventTypeResponse],
)
async def list_event_types(
    host_id: UUID = Depends(get_host_id),
    service: EventTypeService = Depends(
        get_event_type_service,
    ),
):
    event_types = await service.list_event_types(
        host_id,
    )

    return [
        EventTypeResponse.model_validate(event)
        for event in event_types
    ]
# endpoint to get an event type by ID
@router.get(
    "/{event_type_id}",
    response_model=EventTypeResponse,
)
async def get_event_type(
    event_type_id: UUID,
    service: EventTypeService = Depends(
        get_event_type_service,
    ),
):
    event = await service.get_event_type(
        event_type_id,
    )

    return EventTypeResponse.model_validate(
        event,
    )
#endpoint to update an event type by ID
@router.patch(
    "/{event_type_id}",
    response_model=EventTypeResponse,
)
async def update_event_type(
    event_type_id: UUID,
    request: UpdateEventTypeRequest,
    service: EventTypeService = Depends(
        get_event_type_service,
    ),
):
    event = await service.update_event_type(
        event_type_id,
        request,
    )

    return EventTypeResponse.model_validate(
        event,
    )
# router to delete an event type by ID
@router.delete(
    "/{event_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_event_type(
    event_type_id: UUID,
    service: EventTypeService = Depends(
        get_event_type_service,
    ),
):
    await service.delete_event_type(
        event_type_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )