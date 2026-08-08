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