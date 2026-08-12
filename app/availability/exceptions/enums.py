from enum import Enum


class AvailabilityExceptionKind(str, Enum):
    """Kind of availability exception.

    Member names and values deliberately parallel the pure engine's
    ``ExceptionKind`` (``app/slots/slot_generation.py``); the orchestrator maps
    between them by value (ADR-019).
    """

    BLOCK_FULL_DAY = "BLOCK_FULL_DAY"
    BLOCK_PARTIAL = "BLOCK_PARTIAL"
    ADD_WINDOW = "ADD_WINDOW"
