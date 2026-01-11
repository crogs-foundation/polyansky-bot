from datetime import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RouteSchedule
from database.repositories.base import BaseRepository


class BusRouteScheduleRepository(BaseRepository[RouteSchedule]):
    """Repository for bus routes schedule CRUD"""

    def __init__(self, session: AsyncSession):
        super().__init__(RouteSchedule, session)

    async def add(  # Add create method
        self,
        route_number: int,
        departure_time: time,
        service_days: int = 127,
        valid_from: Optional[time] = None,
        valid_until: Optional[time] = None,
        is_active: bool = True,
    ) -> RouteSchedule:
        """Create a new route schedule entry."""
        route_schedule = RouteSchedule(
            route_number=route_number,
            departure_time=departure_time,
            service_days=service_days,
            valid_from=valid_from,
            valid_until=valid_until,
            is_active=is_active,
        )
        self.session.add(route_schedule)
        await self.session.commit()
        await self.session.refresh(route_schedule)
        return route_schedule
