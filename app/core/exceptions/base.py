class ApiException(Exception):
	status_code: int = 500
	message: str = "Internal Server Error"

	def __init__(
		self,
		message: str | None = None,
		*,
		details: list[object] | None = None,
	) -> None:
		self.message = message or self.message
		self.details = details
		super().__init__(self.message)


class ValidationException(ApiException):
	status_code = 400
	message = "Validation Failed"


class ConflictException(ApiException):
	status_code = 409
	message = "Conflict"


class NotFoundException(ApiException):
	status_code = 404
	message = "Resource not found"
