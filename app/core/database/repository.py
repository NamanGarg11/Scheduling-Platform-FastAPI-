from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
	def __init__(
		self,
		session: AsyncSession,
		model: type[ModelT],
	) -> None:
		self.session = session
		self.model = model

	async def save(self, entity: ModelT) -> ModelT:
		self.session.add(entity)
		await self.session.flush()
		await self.session.refresh(entity)
		return entity

	async def delete(self, entity: ModelT) -> None:
		await self.session.delete(entity)
		await self.session.flush()

	async def find_by_id(self, entity_id: object) -> ModelT | None:
		stmt = select(self.model).where(self.model.id == entity_id)
		result = await self.session.execute(stmt)
		return result.scalar_one_or_none()

	async def list(
		self,
		*,
		offset: int = 0,
		limit: int = 100,
		order_by: ColumnElement[object] | None = None,
		filters: Sequence[ColumnElement[bool]] | None = None,
	) -> list[ModelT]:
		stmt: Select[tuple[ModelT]] = select(self.model)

		if filters:
			stmt = stmt.where(*filters)

		if order_by is not None:
			stmt = stmt.order_by(order_by)

		stmt = stmt.offset(offset).limit(limit)

		result = await self.session.execute(stmt)
		return list(result.scalars().all())

	async def exists(
		self,
		*,
		filters: Sequence[ColumnElement[bool]],
	) -> bool:
		stmt = select(func.count()).select_from(self.model).where(*filters)
		count_value = await self.session.scalar(stmt)
		return (count_value or 0) > 0

	async def count(
		self,
		*,
		filters: Sequence[ColumnElement[bool]] | None = None,
	) -> int:
		stmt = select(func.count()).select_from(self.model)
		if filters:
			stmt = stmt.where(*filters)

		count_value = await self.session.scalar(stmt)
		return int(count_value or 0)
