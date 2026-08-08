from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.event_types.enums import LocationType

class CreateEventTypeRequest(BaseModel):

    title: str = Field(
        min_length=3,
        max_length=100,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    duration_minutes: int = Field(
        gt=0,
        le=480,
    )

    location_type: LocationType

    location_value: str | None = Field(
        default=None,
        max_length=255,
    )

    buffer_before_minutes: int = Field(
        default=0,
        ge=0,
        le=120,
    )

    buffer_after_minutes: int = Field(
        default=0,
        ge=0,
        le=120,
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Title cannot be blank.")

        return value

    @field_validator("location_value")
    @classmethod
    def validate_location_value(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Location value cannot be blank.")

        return value

class UpdateEventTypeRequest(BaseModel):

    title: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    duration_minutes: int | None = Field(
        default=None,
        gt=0,
        le=480,
    )

    location_type: LocationType | None = None

    location_value: str | None = Field(
        default=None,
        max_length=255,
    )

    buffer_before_minutes: int | None = Field(
        default=None,
        ge=0,
        le=120,
    )

    buffer_after_minutes: int | None = Field(
        default=None,
        ge=0,
        le=120,
    )

    is_active: bool | None = None

    @field_validator("title")
    @classmethod
    def validate_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Title cannot be blank.")

        return value

    @field_validator("location_value")
    @classmethod
    def validate_optional_location_value(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Location value cannot be blank.")

        return value

class EventTypeResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    host_id: UUID

    title: str

    description: str | None

    slug: str

    duration_minutes: int

    is_active: bool

    location_type: LocationType

    location_value: str | None

    buffer_before_minutes: int

    buffer_after_minutes: int

    created_at: datetime

    updated_at: datetime

    @field_validator("title")
    @classmethod
    def validate_response_title(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Title cannot be blank.")

        return value