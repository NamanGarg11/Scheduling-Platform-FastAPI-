from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
	page: int = Field(default=1, ge=1)
	size: int = Field(default=20, ge=1, le=100)

	@property
	def offset(self) -> int:
		return (self.page - 1) * self.size


class PaginationMeta(BaseModel):
	page: int
	size: int
	total: int
	total_pages: int


class PaginatedResult(BaseModel, Generic[T]):
	items: list[T]
	meta: PaginationMeta


def build_paginated_result(
	*,
	items: list[T],
	total: int,
	page: int,
	size: int,
) -> PaginatedResult[T]:
	total_pages = ceil(total / size) if total > 0 else 0
	return PaginatedResult[T](
		items=items,
		meta=PaginationMeta(
			page=page,
			size=size,
			total=total,
			total_pages=total_pages,
		),
	)
