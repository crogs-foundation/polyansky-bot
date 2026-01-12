from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import List, Optional

import loguru
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import BusRoute, BusStop, RouteStop, StopSchedule


@dataclass
class RouteSegment:
    """Represents one segment of a journey."""

    route_number: str
    origin_stop: BusStop
    destination_stop: BusStop
    departure_time: time
    arrival_time: time
    travel_duration: timedelta


@dataclass
class JourneyOption:
    """Complete journey from origin to destination."""

    segments: List[RouteSegment]
    total_duration: timedelta
    departure_time: time
    arrival_time: time
    transfers: int

    @property
    def is_direct(self) -> bool:
        """Check if journey has no transfers."""
        return len(self.segments) == 1


class RouteFinder:
    """
    Service for finding optimal bus routes between stops.

    Implements simplified route search algorithm.
    For production, consider using graph algorithms (Dijkstra, A*).
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize route finder.

        Args:
            session: Active database session.
        """
        self.session = session

    async def find_routes(
        self,
        origin_code: str,
        destination_code: str,
        departure_time: Optional[time] = None,
        max_results: int = 3,
    ) -> List[JourneyOption]:
        """
        Find possible routes between two stops.

        Args:
            origin_code: Origin bus stop ID.
            destination_code: Destination bus stop ID.
            departure_time: Desired departure time. If None, uses current time.
            max_results: Maximum number of journey options to return.

        Returns:
            List of journey options sorted by total duration.

        Algorithm:
            1. Find all direct routes
            2. If needed, find routes with one transfer
            3. Sort by total time and number of transfers
        """
        if departure_time is None:
            departure_time = datetime.now().time()

        results: List[JourneyOption] = []

        # Step 1: Find direct routes
        direct_routes = await self._find_direct_routes(
            origin_code, destination_code, departure_time
        )
        results.extend(direct_routes)

        # Step 2: If not enough results, find routes with transfers
        if len(results) < max_results:
            transfer_routes = await self._find_routes_with_transfers(
                origin_code, destination_code, departure_time, max_results - len(results)
            )
            results.extend(transfer_routes)

        # Sort by: transfers (fewer better), then duration
        results.sort(key=lambda x: (x.transfers, x.total_duration))

        return results[:max_results]

    async def _find_direct_routes(
        self, origin_code: str, destination_code: str, departure_time: time
    ) -> List[JourneyOption]:
        """
        Find direct routes (no transfers) between stops.

        Strategy:
        1. Find routes that serve both origin and destination stops
        2. Use StopSchedule to get actual arrival times at each stop
        3. Validate the order and timing

        Args:
            origin_code: Origin stop ID.
            destination_code: Destination stop ID.
            departure_time: Minimum departure time.

        Returns:
            List of direct journey options.
        """
        # Query to find routes that have both stops
        stmt = (
            select(BusRoute)
            .join(
                RouteStop,
                BusRoute.route_number == RouteStop.route_number,
            )
            .where(
                and_(
                    RouteStop.stop_code.in_([origin_code, destination_code]),
                    BusRoute.is_active,
                )
            )
            .options(
                selectinload(BusRoute.route_stops).selectinload(RouteStop.bus_stop),
                selectinload(BusRoute.stop_schedules).selectinload(StopSchedule.stop),
            )
            .distinct()
        )

        result = await self.session.execute(stmt)
        routes = result.scalars().all()

        journeys = []
        for route in routes:
            # Create a mapping of stop_code to RouteStop for ordering
            route_stop_map = {rs.stop_code: rs for rs in route.route_stops}

            # Check if both stops exist in the route
            if (
                origin_code not in route_stop_map
                or destination_code not in route_stop_map
            ):
                loguru.logger.debug(
                    f"Route {route.route_number}: origin or destination not in route, skipping"
                )
                continue

            origin_route_stop = route_stop_map[origin_code]
            dest_route_stop = route_stop_map[destination_code]

            # Validate order: destination must come after origin
            if dest_route_stop.stop_order <= origin_route_stop.stop_order:
                loguru.logger.debug(
                    f"Route {route.route_number}: destination before origin, skipping"
                )
                continue

            # Get stop schedules for both stops
            origin_schedules = [
                stop_schedule
                for stop_schedule in route.stop_schedules
                if stop_schedule.stop_code == origin_code and stop_schedule.is_active
            ]
            dest_schedules = [
                stop_schedule
                for stop_schedule in route.stop_schedules
                if stop_schedule.stop_code == destination_code and stop_schedule.is_active
            ]

            if not origin_schedules or not dest_schedules:
                loguru.logger.debug(f"Route {route.route_number}: missing schedules")
                continue

            # Match schedules: for each origin departure, find matching destination arrival
            # Assumption: schedules are paired (same index = same bus trip)
            for orig_sched, dest_sched in zip(origin_schedules, dest_schedules):
                # Filter by departure time
                if orig_sched.arrival_time < departure_time:
                    continue

                # Validate timing: destination arrival must be after origin departure
                if dest_sched.arrival_time <= orig_sched.arrival_time:
                    continue

                # Calculate travel duration
                duration = self._calculate_duration(
                    orig_sched.arrival_time,
                    dest_sched.arrival_time,
                )

                # Get the actual BusStop objects
                origin_stop = origin_route_stop.bus_stop
                destination_stop = dest_route_stop.bus_stop

                segment = RouteSegment(
                    route_number=orig_sched.route_number,
                    origin_stop=origin_stop,
                    destination_stop=destination_stop,
                    departure_time=orig_sched.arrival_time,
                    arrival_time=dest_sched.arrival_time,
                    travel_duration=duration,
                )

                journey = JourneyOption(
                    segments=[segment],
                    total_duration=duration,
                    departure_time=orig_sched.arrival_time,
                    arrival_time=dest_sched.arrival_time,
                    transfers=0,
                )
                journeys.append(journey)

        return journeys

    async def _find_routes_with_transfers(
        self,
        origin_code: str,
        destination_code: str,
        departure_time: time,
        max_results: int,
    ) -> List[JourneyOption]:
        """
        Find routes with one transfer.

        This is a simplified implementation. Production version should:
        - Use graph algorithms for efficiency
        - Consider transfer walking time
        - Handle multiple transfers
        - Cache route networks

        Args:
            origin_code: Origin stop ID.
            destination_code: Destination stop ID.
            departure_time: Minimum departure time.
            max_results: Maximum results to return.

        Returns:
            List of journey options with transfers.
        """
        # Find potential transfer points
        # (stops that are on routes from origin AND routes to destination)

        # This is placeholder logic - implement based on your city's topology
        # For MVP, return empty list
        loguru.logger.info("Transfer routes not yet implemented")
        return []

    @staticmethod
    def _calculate_duration(start: time, end: time) -> timedelta:
        """
        Calculate duration between two times.

        Handles midnight crossing (assumes same day or next day).

        Args:
            start: Start time.
            end: End time.

        Returns:
            Duration as timedelta.
        """
        start_dt = datetime.combine(datetime.today(), start)
        end_dt = datetime.combine(datetime.today(), end)

        if end_dt < start_dt:
            # Next day
            end_dt += timedelta(days=1)

        return end_dt - start_dt
