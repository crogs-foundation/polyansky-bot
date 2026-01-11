# database/repositories/stop_schedule.py
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import StopSchedule
from database.repositories.base import BaseRepository


class BusStopScheduleRepository(BaseRepository[StopSchedule]):
    """Repository for managing stop schedule records."""

    def __init__(self, session: AsyncSession):
        super().__init__(StopSchedule, session)

    async def add(
        self,
        route_number: int,
        stop_code: str,
        arrival_time: time,
        is_active: bool = True,
    ) -> StopSchedule:
        """Create a new stop schedule entry."""
        stop_schedule = StopSchedule(
            route_number=route_number,
            stop_code=stop_code,
            arrival_time=arrival_time,
            is_active=is_active,
        )
        self.session.add(stop_schedule)
        await self.session.commit()
        await self.session.refresh(stop_schedule)
        return stop_schedule

    async def get_by_route_and_stop(
        self, route_number: int, stop_code: str
    ) -> list[StopSchedule]:
        """Get all stop schedules for a specific route and stop."""
        query = await self.session.execute(
            self._get_base_query()
            .filter(StopSchedule.route_number == route_number)
            .filter(StopSchedule.stop_code == stop_code)
            .order_by(StopSchedule.arrival_time)
        )
        return list(query.scalars().all())

    async def get_by_stop_and_time(
        self, stop_code: int, from_time: time, to_time: time
    ) -> list[StopSchedule]:
        """Get all stop schedules for a specific stop within a time range."""
        query = await self.session.execute(
            self._get_base_query()
            .filter(StopSchedule.stop_code == stop_code)
            .filter(StopSchedule.arrival_time >= from_time)
            .filter(StopSchedule.arrival_time <= to_time)
            .order_by(StopSchedule.arrival_time)
        )
        return list(query.scalars().all())

    async def get_active_by_route(self, route_number: int) -> list[StopSchedule]:
        """Get all active stop schedules for a specific route."""
        query = await self.session.execute(
            self._get_base_query()
            .filter(StopSchedule.route_number == route_number)
            .filter(StopSchedule.is_active)
            .order_by(StopSchedule.arrival_time)
        )
        return list(query.scalars().all())
