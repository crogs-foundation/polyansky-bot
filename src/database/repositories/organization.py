"""Repository for organizations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Organization

from .base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """Repository for organization operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Organization, session)

    async def get_by_category(
        self, category_id: int, limit: int = 10, offset: int = 0
    ) -> list[Organization]:
        """Get organizations by category with pagination."""
        stmt = (
            select(Organization)
            .where(Organization.category == category_id)
            .order_by(Organization.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_by_name(self, query: str, limit: int = 10) -> list[Organization]:
        """Search organizations by name."""
        stmt = (
            select(Organization)
            .where(Organization.name.ilike(f"%{query}%"))
            .order_by(Organization.name)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_category(self, category_id: int) -> int:
        """Count organizations in a category."""
        stmt = select(Organization).where(Organization.category == category_id)
        result = await self.session.execute(stmt)
        return len(list(result.scalars().all()))

    async def count(self) -> int:
        """Count total number of organizations."""
        stmt = select(Organization)
        result = await self.session.execute(stmt)
        return len(list(result.scalars().all()))
