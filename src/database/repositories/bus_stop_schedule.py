# database/repositories/stop_schedule.py
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import StopSchedule
from database.repositories.base import BaseRepository
from utils.service_days import parse_service_days


class BusStopScheduleRepository(BaseRepository[StopSchedule]):
    """Repository for managing stop schedule records."""

    def __init__(self, session: AsyncSession):
        super().__init__(StopSchedule, session)

    async def add(
        self,
        route_name: str,
        stop_code: str,
        arrival_time: time,
        service_days: int,
        is_active: bool = True,
    ) -> StopSchedule:
        """Create a new stop schedule entry."""
        monday, tuesday, wednesday, thursday, friday, saturday, sunday = (
            parse_service_days(service_days)
        )
        stop_schedule = StopSchedule(
            route_name=route_name,
            stop_code=stop_code,
            arrival_time=arrival_time,
            is_active=is_active,
            monday=monday,
            tuesday=tuesday,
            wednesday=wednesday,
            thursday=thursday,
            friday=friday,
            saturday=saturday,
            sunday=sunday,
        )
        self.session.add(stop_schedule)
        await self.session.commit()
        await self.session.refresh(stop_schedule)
        return stop_schedule

    async def add_bulk(self, stop_schedules_data: list[dict]) -> None:
        """Bulk create stop schedule entries."""
        stop_schedules = []
        for data in stop_schedules_data:
            monday, tuesday, wednesday, thursday, friday, saturday, sunday = (
                parse_service_days(data["service_days"])
            )
            stop_schedules.append(
                StopSchedule(
                    route_name=data["route_name"],
                    stop_code=data["stop_code"],
                    arrival_time=data["arrival_time"],
                    is_active=data.get("is_active", True),
                    monday=monday,
                    tuesday=tuesday,
                    wednesday=wednesday,
                    thursday=thursday,
                    friday=friday,
                    saturday=saturday,
                    sunday=sunday,
                )
            )

        self.session.add_all(stop_schedules)
        await self.session.commit()

    async def get_by_route_and_stop(
        self, route_name: str, stop_code: str
    ) -> list[StopSchedule]:
        """Get all stop schedules for a specific route and stop."""
        query = await self.session.execute(
            self._get_base_query()
            .filter(StopSchedule.route_name == route_name)
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

    async def get_active_by_route(self, route_name: str) -> list[StopSchedule]:
        """Get all active stop schedules for a specific route."""
        query = await self.session.execute(
            self._get_base_query()
            .filter(StopSchedule.route_name == route_name)
            .filter(StopSchedule.is_active)
            .order_by(StopSchedule.arrival_time)
        )
        return list(query.scalars().all())
