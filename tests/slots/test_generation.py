from datetime import date, time

from app.availability.enums import DayOfWeek
from app.availability.model import Availability
from app.event_types.model import EventType
from app.event_types.enums import LocationType
from app.slots.slot_generation import SlotGenerationEngine


def test_generates_slots_with_buffers():
    event_type = EventType(
        title="Consultation",
        description=None,
        slug="consultation",
        duration_minutes=30,
        is_active=True,
        location_type=LocationType.ZOOM,
        location_value=None,
        buffer_before_minutes=5,
        buffer_after_minutes=10,
        host_id=None,
    )

    availability = Availability(
        host_id=None,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(12, 0),
        is_available=True,
    )

    engine = SlotGenerationEngine()

    slots = engine.generate(
        event_type=event_type,
        availability=[availability],
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 10),
        timezone="Asia/Kolkata",
    )

    assert len(slots) == 4

    assert slots[0].start_at.hour == 9
    assert slots[0].start_at.minute == 5

    assert slots[0].end_at.hour == 9
    assert slots[0].end_at.minute == 35