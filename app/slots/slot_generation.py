from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.availability.enums import DayOfWeek
from app.availability.model import Availability
from app.event_types.model import EventType


@dataclass(frozen=True, slots=True)
class SlotCandidate:
    start_at: datetime
    end_at: datetime


class SlotGenerationEngine:
    """
    Pure scheduling engine.

    This class has no knowledge of:
    - FastAPI
    - SQLAlchemy sessions
    - repositories
    - HTTP
    - database transactions

    It only converts:
        EventType + Availability + Date range
    into:
        SlotCandidate objects.
    """

    def generate(
        self,
        *,
        event_type: EventType,
        availability: list[Availability],
        start_date: date,
        end_date: date,
        timezone: str,
    ) -> list[SlotCandidate]:

        if start_date > end_date:
            raise ValueError(
                "start_date cannot be after end_date."
            )

        timezone_info = ZoneInfo(timezone)

        candidates: list[SlotCandidate] = []

        current_date = start_date

        while current_date <= end_date:

            day_of_week = DayOfWeek(
                current_date.strftime("%A").upper()
            )

            daily_availability = [
                item
                for item in availability
                if (
                    item.day_of_week == day_of_week
                    and item.is_available
                )
            ]

            for availability_window in daily_availability:

                candidates.extend(
                    self._generate_for_window(
                        event_type=event_type,
                        availability=availability_window,
                        current_date=current_date,
                        timezone=timezone_info,
                    )
                )

            current_date += timedelta(days=1)

        return candidates

    def _generate_for_window(
        self,
        *,
        event_type: EventType,
        availability: Availability,
        current_date: date,
        timezone: ZoneInfo,
    ) -> list[SlotCandidate]:

        window_start = datetime.combine(
            current_date,
            availability.start_time,
            tzinfo=timezone,
        )

        window_end = datetime.combine(
            current_date,
            availability.end_time,
            tzinfo=timezone,
        )

        if window_start >= window_end:
            return []

        duration = timedelta(
            minutes=event_type.duration_minutes,
        )

        buffer_before = timedelta(
            minutes=event_type.buffer_before_minutes,
        )

        buffer_after = timedelta(
            minutes=event_type.buffer_after_minutes,
        )

        occupied_duration = (
            buffer_before
            + duration
            + buffer_after
        )

        candidates: list[SlotCandidate] = []

        current_start = window_start

        while (
            current_start + occupied_duration
            <= window_end
        ):

            actual_start = (
                current_start + buffer_before
            )

            actual_end = (
                actual_start + duration
            )

            candidates.append(
                SlotCandidate(
                    start_at=actual_start,
                    end_at=actual_end,
                )
            )

            current_start += occupied_duration

        return candidates