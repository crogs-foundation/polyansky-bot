# database/repositories/base.py
from typing import Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository class with common CRUD operations."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    def _get_base_query(self):
        """Get base select query for the model."""
        return select(self.model)

    async def create(self, **kwargs) -> ModelType:
        """Create a new record."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def get(self, id: int) -> ModelType | None:
        """Get record by ID."""
        query = select(self.model).where(self.model.id == id)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_all(self, limit: int | None = None, offset: int = 0) -> list[ModelType]:
        """Get all records."""
        query = select(self.model).offset(offset)
        if limit is not None:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(self, id: int, **kwargs) -> ModelType | None:
        """Update record by ID."""
        instance = await self.get(id)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await self.session.commit()
            await self.session.refresh(instance)
        return instance

    async def delete(self, id: int) -> bool:
        """Delete record by ID."""
        instance = await self.get(id)
        if instance:
            await self.session.delete(instance)
            await self.session.commit()
            return True
        return False
