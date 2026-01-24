"""Repository for organization categories."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import OrganizationCategory

from .base import BaseRepository


class OrganizationCategoryRepository(BaseRepository[OrganizationCategory]):
    """Repository for organization category operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(OrganizationCategory, session)

    async def get_by_name(self, name: str) -> Optional[OrganizationCategory]:
        """Get category by name."""
        stmt = select(OrganizationCategory).where(OrganizationCategory.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count(self) -> int:
        """Count total number of categories."""
        stmt = select(OrganizationCategory)
        result = await self.session.execute(stmt)
        return len(list(result.scalars().all()))
