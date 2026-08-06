from uuid import UUID

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, PaginatedResult, build_paginated_result
from app.users.model import User
from app.users.repository import UserRepository
from app.users.schema import CreateUserRequest, UpdateUserRequest
from app.utils.slug import slugify

logger = get_logger(__name__)


class UserService:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self.repository = repository

    async def create_user(
        self,
        request: CreateUserRequest,
    ) -> User:
        existing = await self.repository.find_by_email(str(request.email))
        if existing:
            raise ConflictException("Email already exists.")

        slug = await self.generate_unique_slug(request.name)

        user = User(
            name=request.name,
            email=str(request.email),
            timezone=request.timezone or "UTC",
            slug=slug,
        )

        created = await self.repository.save(user)
        logger.info("Created user: id=%s email=%s", created.id, created.email)
        return created

    async def get_user(
        self,
        user_id: UUID,
    ) -> User:
        user = await self.repository.find_by_id(user_id)
        if not user:
            raise NotFoundException("User not found.")

        return user

    async def list_users(
        self,
        pagination: PaginationParams,
    ) -> PaginatedResult[User]:
        items = await self.repository.list(
            offset=pagination.offset,
            limit=pagination.size,
            order_by=User.created_at.desc(),
        )
        total = await self.repository.count()
        return build_paginated_result(
            items=items,
            total=total,
            page=pagination.page,
            size=pagination.size,
        )

    async def update_user(
        self,
        user_id: UUID,
        request: UpdateUserRequest,
    ) -> User:
        user = await self.get_user(user_id)

        if request.email is not None:
            existing = await self.repository.find_by_email(str(request.email))
            if existing and existing.id != user.id:
                raise ConflictException("Email already exists.")
            user.email = str(request.email)

        if request.name is not None:
            user.name = request.name
            user.slug = await self.generate_unique_slug(
                request.name,
                exclude_user_id=user.id,
            )

        if request.timezone is not None:
            user.timezone = request.timezone

        updated = await self.repository.save(user)
        logger.info("Updated user: id=%s", updated.id)
        return updated

    async def delete_user(
        self,
        user_id: UUID,
    ) -> None:
        user = await self.get_user(user_id)
        await self.repository.delete(user)
        logger.info("Deleted user: id=%s", user.id)

    async def generate_unique_slug(
        self,
        name: str,
        *,
        exclude_user_id: UUID | None = None,
    ) -> str:

        base_slug = slugify(name)
        if not base_slug:
            raise ValidationException("Name must contain at least one alphanumeric character.")

        slug = base_slug
        counter = 2

        while True:
            existing = await self.repository.find_by_slug(slug)
            if not existing:
                return slug
            if exclude_user_id is not None and existing.id == exclude_user_id:
                return slug
            slug = f"{base_slug}-{counter}"
            counter += 1