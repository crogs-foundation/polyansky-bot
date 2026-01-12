from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RouteSchedule
from database.repositories.base import BaseRepository
from utils.service_days import parse_service_days


class BusRouteScheduleRepository(BaseRepository[RouteSchedule]):
    """Repository for bus routes schedule CRUD"""

    def __init__(self, session: AsyncSession):
        super().__init__(RouteSchedule, session)

    async def add(  # Add create method
        self,
        route_number: int,
        departure_time: time,
        service_days: int = 127,
        is_active: bool = True,
    ) -> RouteSchedule:
        """Create a new route schedule entry."""
        monday, tuesday, wednesday, thursday, friday, saturday, sunday = (
            parse_service_days(service_days)
        )

        route_schedule = RouteSchedule(
            route_number=route_number,
            departure_time=departure_time,
            is_active=is_active,
            monday=monday,
            tuesday=tuesday,
            wednesday=wednesday,
            thursday=thursday,
            friday=friday,
            saturday=saturday,
            sunday=sunday,
        )
        self.session.add(route_schedule)
        await self.session.commit()
        await self.session.refresh(route_schedule)
        return route_schedule
