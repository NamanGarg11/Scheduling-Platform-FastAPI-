from contextlib import asynccontextmanager

from fastapi import FastAPI

# Included BEFORE the availability router so GET /availability/exceptions is not
# shadowed by GET /availability/{availability_id} (UUID parse -> 422). See ADR-019.
from app.availability.exceptions.router import (
    router as availability_exception_router,
)
from app.availability.router import (
    router as availability_router,
)
from app.bookings.router import router as booking_router
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.response import ApiResponse
from app.event_types.router import (
    router as event_type_router,
)
from app.slots.public_router import router as public_slot_router
from app.slots.router import router as slot_router
from app.users.router import router as user_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


app = FastAPI(
    title="Scheduling Platform API",
    description="Backend API for Scheduling Platform Assignment",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

register_exception_handlers(app)


@app.get("/health", response_model=ApiResponse[dict[str, str]])
async def health() -> ApiResponse[dict[str, str]]:
    return ApiResponse(
        success=True,
        message="Service is healthy.",
        data={
            "status": "ok",
            "service": "Scheduling Platform API",
            "version": "1.0.0",
        },
    )


app.include_router(user_router)
app.include_router(
    event_type_router,
)
app.include_router(
    availability_exception_router,
)
app.include_router(
    availability_router,
)
app.include_router(slot_router)
app.include_router(public_slot_router)
app.include_router(
    booking_router,
)