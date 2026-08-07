from datetime import time
from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.availability.enums import DayOfWeek
#  dto to create the availability 
class CreateAvailabilityRequest(BaseModel):

    day_of_week: DayOfWeek

    start_time: time

    end_time: time

    is_available: bool = True

    @model_validator(mode="after")
    def validate_time_range(self):

        if (
            self.is_available
            and self.start_time >= self.end_time
        ):
            raise ValueError(
                "Start time must be before end time."
            )

        return self
# dto to update the availability
class UpdateAvailabilityRequest(BaseModel):

    start_time: time | None = None

    end_time: time | None = None

    is_available: bool | None = None

    @model_validator(mode="after")
    def validate_time_range(self):

        if (
            self.start_time
            and self.end_time
            and self.start_time >= self.end_time
        ):
            raise ValueError(
                "Start time must be before end time."
            )

        return self

# dto to return the availability response 
class AvailabilityResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    host_id: UUID

    day_of_week: DayOfWeek

    start_time: time

    end_time: time

    is_available: bool

    created_at: datetime

    updated_at: datetime