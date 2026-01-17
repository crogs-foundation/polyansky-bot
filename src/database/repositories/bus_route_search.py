from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RouteSearch
from database.repositories.base import BaseRepository


class BusRouteSearchRepository(BaseRepository[RouteSearch]):
    """Repository for bus route CRUD"""

    def __init__(self, session: AsyncSession):
        super().__init__(RouteSearch, session)

    async def last(self, user_id: int) -> RouteSearch | None:
        query = await self.session.execute(
            select(RouteSearch)
            .where(RouteSearch.telegram_user_id == user_id)
            .order_by(RouteSearch.created_at.desc())
        )

        return query.scalars().first()
