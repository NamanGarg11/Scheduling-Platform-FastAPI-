from enum import StrEnum


class LocationType(StrEnum):
    GOOGLE_MEET = "google_meet"
    ZOOM = "zoom"
    MICROSOFT_TEAMS = "microsoft_teams"
    PHONE = "phone"
    IN_PERSON = "in_person"
    CUSTOM = "custom"