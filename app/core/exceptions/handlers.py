from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions.base import ApiException, ValidationException
from app.core.response import ErrorResponse


def register_exception_handlers(app: FastAPI) -> None:
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
		mapped = ValidationException(details=list(exc.errors()))
		return JSONResponse(
			status_code=mapped.status_code,
			content=ErrorResponse(
				message=mapped.message,
				details=mapped.details,
			).model_dump(),
		)
