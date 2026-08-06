from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_user_service
from app.core.pagination import PaginationParams, PaginatedResult
from app.core.response import ApiResponse
from app.users.schema import CreateUserRequest, UpdateUserRequest, UserResponse
from app.users.service import UserService

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    request: CreateUserRequest,
    service: UserService = Depends(
        get_user_service
    ),
)-> ApiResponse[UserResponse]:
    user = await service.create_user(request)
    return ApiResponse(
        success=True,
        message="User created successfully.",
        data=UserResponse.model_validate(user),
    )


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserResponse],
)
async def get_user(
    user_id: UUID,
    service: UserService = Depends(
        get_user_service
    ),
)-> ApiResponse[UserResponse]:
    user = await service.get_user(user_id)
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user),
    )


@router.get(
    "",
    response_model=ApiResponse[PaginatedResult[UserResponse]],
)
async def list_users(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: UserService = Depends(
        get_user_service
    ),
) -> ApiResponse[PaginatedResult[UserResponse]]:
    result = await service.list_users(PaginationParams(page=page, size=size))
    response_payload = PaginatedResult[UserResponse](
        items=[UserResponse.model_validate(u) for u in result.items],
        meta=result.meta,
    )
    return ApiResponse(
        success=True,
        data=response_payload,
    )


@router.patch(
    "/{user_id}",
    response_model=ApiResponse[UserResponse],
)
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,
    service: UserService = Depends(
        get_user_service
    ),
)-> ApiResponse[UserResponse]:
    user = await service.update_user(user_id, request)
    return ApiResponse(
        success=True,
        message="User updated successfully.",
        data=UserResponse.model_validate(user),
    )


@router.delete(
    "/{user_id}",
    response_model=ApiResponse[None],
)
async def delete_user(
    user_id: UUID,
    service: UserService = Depends(
        get_user_service
    ),
)-> ApiResponse[None]:
    await service.delete_user(user_id)
    return ApiResponse(
        success=True,
        message="User deleted successfully.",
    )