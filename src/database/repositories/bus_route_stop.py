from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RouteStop
from database.repositories.base import BaseRepository


class BusRouteStopRepository(BaseRepository[RouteStop]):
    """Repository for bus schedule CRUD"""

    def __init__(self, session: AsyncSession):
        super().__init__(RouteStop, session)

    async def add(  # Add create method
        self,
        route_number: int,
        stop_code: str,
        stop_order: int,
    ) -> RouteStop:
        """Create a new route stop entry."""
        route_stop = RouteStop(
            route_number=route_number,
            stop_code=stop_code,
            stop_order=stop_order,
        )
        self.session.add(route_stop)
        await self.session.commit()
        await self.session.refresh(route_stop)
        return route_stop
