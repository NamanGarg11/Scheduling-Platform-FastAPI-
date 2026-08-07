from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions.base import (
    ApiException,
    ValidationException,
)
from app.core.logging import get_logger
from app.core.response import ErrorResponse

logger = get_logger(__name__)


def register_exception_handlers(
    app: FastAPI,
) -> None:
    """
    Register all application exception handlers.
    """

    @app.exception_handler(ApiException)
    async def api_exception_handler(
        request: Request,
        exc: ApiException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                message=exc.message,
                details=exc.details,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        mapped = ValidationException(
            details=exc.errors(),
        )

        return JSONResponse(
            status_code=mapped.status_code,
            content=ErrorResponse(
                message=mapped.message,
                details=mapped.details,
            ).model_dump(),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:

        logger.exception(
            "Database exception while processing %s %s",
            request.method,
            request.url.path,
        )

        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                message="Database Error",
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:

        logger.exception(
            "Unhandled exception while processing %s %s",
            request.method,
            request.url.path,
        )

        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                message="Internal Server Error",
            ).model_dump(),
        )