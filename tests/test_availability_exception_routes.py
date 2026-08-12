"""Route-order guard (ADR-019).

The exceptions router must be included before the availability router so that
GET /availability/exceptions is not shadowed by GET /availability/{availability_id}
(which would fail UUID parsing with 422). This test runs without a database.
"""

from app.main import app


def _flatten_routes(routes):
    """Unwrap FastAPI's lazy _IncludedRouter wrappers (0.141+)."""
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _flatten_routes(original_router.routes)
        else:
            yield route


def test_exceptions_list_route_precedes_availability_param_route() -> None:
    paths = [getattr(route, "path", "") for route in _flatten_routes(app.routes)]

    assert "/availability/exceptions" in paths
    assert "/availability/{availability_id}" in paths

    exceptions_index = paths.index("/availability/exceptions")
    availability_index = paths.index("/availability/{availability_id}")

    assert exceptions_index < availability_index, (
        "GET /availability/exceptions would be shadowed by "
        "GET /availability/{availability_id}"
    )
