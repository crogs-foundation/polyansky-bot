from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import BusRoute, BusStop, RouteStop


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
            origin_id: Origin bus stop ID.
            destination_id: Destination bus stop ID.
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

        Args:
            origin_id: Origin stop ID.
            destination_id: Destination stop ID.
            departure_time: Minimum departure time.

        Returns:
            List of direct journey options.
        """
        # Find routes that contain both stops in correct order
        stmt = (
            select(BusRoute)
            .join(RouteStop, BusRoute.route_number == RouteStop.route_number)
            .where(
                RouteStop.bus_stop_code.in_([origin_code, destination_code]),
            )
            .options(selectinload(BusRoute.route_stops).selectinload(RouteStop.bus_stop))
            .distinct()
        )

        result = await self.session.execute(stmt)
        routes = result.scalars().all()

        journeys = []
        for route in routes:
            # Find origin and destination in this route
            origin_schedule = None
            dest_schedule = None

            for schedule in sorted(route.schedules, key=lambda s: s.stop_order):
                if schedule.bus_stop_code == origin_code and schedule.is_active:
                    origin_schedule = schedule
                elif (
                    schedule.bus_stop_code == destination_code
                    and schedule.is_key_stop
                    and origin_schedule is not None
                ):
                    dest_schedule = schedule
                    break

            # Validate route direction and timing
            if origin_schedule and dest_schedule:
                if dest_schedule.stop_order > origin_schedule.stop_order:
                    if origin_schedule.departure_time >= departure_time:
                        # Calculate travel duration
                        duration = self._calculate_duration(
                            origin_schedule.departure_time,
                            dest_schedule.departure_time,
                        )

                        segment = RouteSegment(
                            route_number=route.route_number,
                            origin_stop=origin_schedule.bus_stop,
                            destination_stop=dest_schedule.bus_stop,
                            departure_time=origin_schedule.departure_time,
                            arrival_time=dest_schedule.departure_time,
                            travel_duration=duration,
                        )

                        journey = JourneyOption(
                            segments=[segment],
                            total_duration=duration,
                            departure_time=origin_schedule.departure_time,
                            arrival_time=dest_schedule.departure_time,
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
            origin_id: Origin stop ID.
            destination_id: Destination stop ID.
            departure_time: Minimum departure time.
            max_results: Maximum results to return.

        Returns:
            List of journey options with transfers.
        """
        # Find potential transfer points
        # (stops that are on routes from origin AND routes to destination)

        # This is placeholder logic - implement based on your city's topology
        # For MVP, return empty list
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
