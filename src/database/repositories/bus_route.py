from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BusRoute
from database.repositories.base import BaseRepository


class BusRouteRepository(BaseRepository[BusRoute]):
    """Repository for bus route CRUD"""

    def __init__(self, session: AsyncSession):
        super().__init__(BusRoute, session)

    async def get_by_name(self, route_name: int) -> BusRoute | None:
        """
        Search bus stops by name (case-insensitive substring match).

        Args:
            query: Search term.
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of matching bus stops ordered by relevance.
        """

        stmt = select(BusRoute).where(BusRoute.name == route_name)

        result = await self.session.execute(stmt)
        return result.scalars().first()
