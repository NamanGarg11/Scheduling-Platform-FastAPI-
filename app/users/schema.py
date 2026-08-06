from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateUserRequest(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=100,
    )

    email: EmailStr

    timezone: str = Field(default="UTC", min_length=1, max_length=80)


class UpdateUserRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=80)


class UserResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    name: str

    email: EmailStr

    slug: str

    timezone: str