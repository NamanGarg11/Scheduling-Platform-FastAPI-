from datetime import date, datetime, time
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.availability.exceptions.enums import AvailabilityExceptionKind

_TIME_REQUIRED_KINDS = (
    AvailabilityExceptionKind.BLOCK_PARTIAL,
    AvailabilityExceptionKind.ADD_WINDOW,
)


class CreateAvailabilityExceptionRequest(BaseModel):
    """Create a one-off availability exception (ADR-020)."""

    model_config = ConfigDict(extra="forbid")

    kind: AvailabilityExceptionKind

    exception_date: date = Field(alias="date")

    start_time: time | None = None

    end_time: time | None = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.kind in _TIME_REQUIRED_KINDS:
            if self.start_time is None or self.end_time is None:
                raise ValueError(
                    f"{self.kind.value} requires start_time and end_time."
                )
            if self.start_time >= self.end_time:
                raise ValueError(
                    "Start time must be before end time."
                )
        elif self.kind == AvailabilityExceptionKind.BLOCK_FULL_DAY:
            if self.start_time is not None or self.end_time is not None:
                raise ValueError(
                    "BLOCK_FULL_DAY must not have start_time or end_time."
                )
        return self


class UpdateAvailabilityExceptionRequest(BaseModel):
    """Update an availability exception (ADR-020)."""

    model_config = ConfigDict(extra="forbid")

    kind: AvailabilityExceptionKind | None = None

    exception_date: date | None = Field(default=None, alias="date")

    start_time: time | None = None

    end_time: time | None = None

    @model_validator(mode="after")
    def validate_times(self):
        kind = self.kind
        start_time = self.start_time
        end_time = self.end_time

        if kind is None:
            if (start_time is None) != (end_time is None):
                raise ValueError(
                    "start_time and end_time must be provided together."
                )
            if (
                start_time is not None
                and end_time is not None
                and start_time >= end_time
            ):
                raise ValueError(
                    "Start time must be before end time."
                )
            return self

        if kind in _TIME_REQUIRED_KINDS:
            if start_time is None or end_time is None:
                raise ValueError(
                    f"{kind.value} requires start_time and end_time."
                )
            if start_time >= end_time:
                raise ValueError(
                    "Start time must be before end time."
                )
        elif kind == AvailabilityExceptionKind.BLOCK_FULL_DAY:
            if start_time is not None or end_time is not None:
                raise ValueError(
                    "BLOCK_FULL_DAY must not have start_time or end_time."
                )
        return self


class AvailabilityExceptionResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    host_id: UUID

    kind: AvailabilityExceptionKind

    exception_date: date = Field(
        validation_alias="exception_date",
        serialization_alias="date",
    )

    start_time: time | None

    end_time: time | None

    created_at: datetime

    updated_at: datetime
