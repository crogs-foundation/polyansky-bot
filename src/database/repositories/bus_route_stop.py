import loguru
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import BusStop, RouteStop
from database.repositories.base import BaseRepository

logger = loguru.logger.bind(name=__name__)

class BusRouteStopRepository(BaseRepository[RouteStop]):
    """Repository for bus schedule CRUD"""

    def __init__(self, session: AsyncSession):
        super().__init__(RouteStop, session)

    async def add(  # Add create method
        self,
        route_name: str,
        stop_code: str,
        stop_order: int,
    ) -> RouteStop:
        """Create a new route stop entry."""
        route_stop = RouteStop(
            route_name=route_name,
            stop_code=stop_code,
            stop_order=stop_order,
        )
        self.session.add(route_stop)
        await self.session.commit()
        await self.session.refresh(route_stop)
        return route_stop

    async def get_stops(
        self,
        route_name: str,
        origin_stop: str | None = None,
        destination_stop: str | None = None,
    ) -> list[BusStop]:
        logger.debug(f"Get stops args: {route_name=}, {origin_stop=}, {destination_stop=}")
        all_route_stops = list(
            (
                await self.session.execute(
                    select(RouteStop)
                    .where(RouteStop.route_name == route_name)
                    .options(
                        selectinload(RouteStop.bus_stop),
                    )
                )
            )
            .scalars()
            .all()
        )

        logger.debug(f"{all_route_stops=}")

        stops = []
        reached_first = False

        for route_stop in sorted(
            all_route_stops, key=lambda route_stop: route_stop.stop_order
        ):
            if route_stop.stop_code == origin_stop:
                reached_first = True

            if not reached_first:
                continue

            stops.append(route_stop.bus_stop)
            if route_stop.stop_code == destination_stop:
                break

        logger.debug(f"{stops=}")
        return stops
