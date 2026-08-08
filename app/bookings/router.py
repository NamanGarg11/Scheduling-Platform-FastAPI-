from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from app.api.deps import get_booking_service
from app.bookings.schema import (
    BookingResponse,
    CreateBookingRequest,
    build_booking_response,
)
from app.bookings.service import BookingService

router = APIRouter(
    prefix="/bookings",
    tags=["Bookings"],
)


def get_host_id(
    x_user_id: UUID = Header(
        alias="x-user-id",
    ),
) -> UUID:
    return x_user_id


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking(
    request: CreateBookingRequest,
    service: BookingService = Depends(
        get_booking_service,
    ),
) -> BookingResponse:

    booking = await service.create_booking(
        request,
    )

    return build_booking_response(
        booking,
    )


@router.get(
    "",
    response_model=list[BookingResponse],
)
async def list_bookings(
    host_id: UUID = Depends(
        get_host_id,
    ),
    service: BookingService = Depends(
        get_booking_service,
    ),
) -> list[BookingResponse]:

    bookings = await service.list_bookings(
        host_id,
    )

    return [
        build_booking_response(
            booking,
        )
        for booking in bookings
    ]
