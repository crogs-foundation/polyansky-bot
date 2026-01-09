"""Base repository with common CRUD operations."""

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy import func, select  # FIXED: Added func import
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic base repository implementing common database operations.

    Type-safe CRUD operations with async/await support.
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class.
            session: Active database session.
        """
        self.model = model
        self.session = session

    async def get(self, id: int) -> Optional[ModelType]:
        """
        Get entity by ID.

        Args:
            id: Primary key value.

        Returns:
            Entity instance or None if not found.
        """
        return await self.session.get(self.model, id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
        """
        Get all entities with pagination.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            List of entity instances.
        """
        query = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelType:
        """
        Create new entity.

        Args:
            **kwargs: Entity attributes.

        Returns:
            Created entity instance with generated ID.
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """
        Update existing entity.

        Args:
            id: Primary key value.
            **kwargs: Attributes to update.

        Returns:
            Updated entity or None if not found.
        """
        instance = await self.get(id)
        if instance is None:
            return None

        for key, value in kwargs.items():
            setattr(instance, key, value)

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: int) -> bool:
        """
        Delete entity by ID.

        Args:
            id: Primary key value.

        Returns:
            True if entity was deleted, False if not found.
        """
        instance = await self.get(id)
        if instance is None:
            return False

        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def count(self) -> int:
        """
        Count total number of entities.

        Returns:
            Total count of records in table.
        """
        query = select(func.count()).select_from(self.model)
        result = await self.session.execute(query)
        return result.scalar_one()
