from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
	success: bool = True
	message: str | None = None
	data: T | None = None


class ErrorResponse(BaseModel):
	success: bool = False
	message: str
	details: list[object] | None = None
