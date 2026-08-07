from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.response import ApiResponse
from app.users.router import router as user_router
from app.event_types.router import (
    router as event_type_router,
)
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