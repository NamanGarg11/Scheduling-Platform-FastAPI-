from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.slots.enums import SlotStatus


class GenerateSlotsRequest(BaseModel):
    """
    Request to generate bookable slots for an event type
    over a specific date range.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    event_type_id: UUID

    start_date: date

    end_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "GenerateSlotsRequest":
        if self.start_date > self.end_date:
            raise ValueError(
                "start_date cannot be after end_date."
            )

        return self


class SlotResponse(BaseModel):
    """
    Representation of a persisted scheduling slot.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    host_id: UUID

    event_type_id: UUID

    start_at: datetime

    end_at: datetime

    status: SlotStatus

    created_at: datetime

    updated_at: datetime


class SlotListResponse(BaseModel):
    """
    Paginated collection of slots.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    items: list[SlotResponse]

    total: int

    page: int = Field(
        ge=1,
    )

    page_size: int = Field(
        ge=1,
        le=100,
    )

    total_pages: int = Field(
        ge=0,
    )


class SlotGenerationResponse(BaseModel):
    """
    Result of a slot generation operation.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    event_type_id: UUID

    start_date: date

    end_date: date

    generated_count: int = Field(
        ge=0,
    )

    skipped_count: int = Field(
        ge=0,
    )

    slots: list[SlotResponse]


class RegenerateSlotsRequest(BaseModel):
    """
    Trigger host-wide slot regeneration over an optional date range.

    Dates are host-local inclusive calendar dates; the range is expanded to
    ``[from 00:00, (to+1) 00:00)`` in the host's timezone and converted to UTC
    (ADR-021).
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    from_date: date | None = None

    to_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "RegenerateSlotsRequest":
        if (
            self.from_date is not None
            and self.to_date is not None
            and self.from_date > self.to_date
        ):
            raise ValueError(
                "from_date cannot be after to_date."
            )

        return self


class SlotRegenerationResponse(BaseModel):
    """
    Result of a host-wide slot regeneration (ADR-021).
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    host_id: UUID

    from_date: date

    to_date: date

    timezone: str

    generated_count: int = Field(
        ge=0,
    )

    restored_count: int = Field(
        ge=0,
    )

    blocked_count: int = Field(
        ge=0,
    )

    kept_count: int = Field(
        ge=0,
    )

    booked_count: int = Field(
        ge=0,
    )