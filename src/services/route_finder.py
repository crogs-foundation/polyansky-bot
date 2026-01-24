import time as time_module
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional, Self, Sequence

import loguru
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import BusRoute, BusStop, RouteStop, StopSchedule


@dataclass
class RouteSegment:
    """Represents one segment of a journey."""

    route_name: str
    origin_stop: BusStop
    destination_stop: BusStop
    departure_time: time
    arrival_time: time
    travel_duration: timedelta


@dataclass
class JourneyOption:
    """Complete journey from origin to destination."""

    segments: list[RouteSegment]
    total_duration: timedelta
    departure_time: time
    arrival_time: time
    transfers: int

    @property
    def is_direct(self) -> bool:
        """Check if journey has no transfers."""
        return len(self.segments) == 1

    def get_key(self) -> tuple:
        """Get unique key for deduplication."""
        return (
            tuple(seg.route_name for seg in self.segments),
            self.departure_time,
            self.arrival_time,
        )

    def __lt__(self, other: Self) -> bool:
        return (
            self.transfers < other.transfers
            or self.total_duration < other.total_duration
            or self.departure_time < other.departure_time
            or self.arrival_time < other.arrival_time
        )


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

    @contextmanager
    def _timer(self, name: str):
        """Context manager to time code execution."""
        start = time_module.time()
        yield
        loguru.logger.debug(f"{name} took {time_module.time() - start:.2f}s")

    async def find_routes(
        self,
        origin_name: str,
        destination_name: str,
        departure_time: Optional[time] = None,
        max_results: int = 3,
    ) -> list[JourneyOption]:
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

        results: list[JourneyOption] = []

        # Step 1: Find direct routes
        with self._timer("Direct routes search"):
            direct_routes = await self._find_direct_routes(
                origin_name, destination_name, departure_time
            )
        results.extend(direct_routes)

        # Step 2: If not enough results, find routes with transfers
        if len(results) < max_results:
            with self._timer("Transfer routes search"):
                transfer_routes = await self._find_routes_with_transfers(
                    origin_name,
                    destination_name,
                    departure_time,
                    max_results - len(results),
                )
            results.extend(transfer_routes)

        results = sorted(results)

        return results[:max_results]

    async def _find_direct_routes(
        self, origin_name: str, destination_name: str, departure_time: time
    ) -> list[JourneyOption]:
        """
        Find direct routes (no transfers) between stops.

        Handles routes that may visit the same stop multiple times (e.g., circular routes).
        For each trip, we find all occurrences of origin and destination stops,
        then consider valid pairs where destination comes after origin.

        Args:
            origin_name: Origin stop name.
            destination_name: Destination stop name.
            departure_time: Minimum departure time.

        Returns:
            List of direct journey options.
        """
        # Get current day of week for filtering
        current_day = datetime.now().strftime("%A").lower()  # "monday", "tuesday", etc.

        loguru.logger.debug(
            f"Finding direct routes from '{origin_name}' to '{destination_name}' "
            f"starting from {departure_time} on {current_day}"
        )

        # Query to find routes that contain BOTH origin and destination stops
        stmt = (
            select(BusRoute)
            .join(RouteStop, BusRoute.name == RouteStop.route_name)
            .join(BusStop, RouteStop.stop_code == BusStop.code)
            .where(
                and_(
                    BusStop.name.in_([origin_name, destination_name]),
                    BusRoute.is_active,
                )
            )
            .group_by(BusRoute.id)
            .having(func.count(func.distinct(BusStop.name)) == 2)
            .options(
                selectinload(BusRoute.route_stops).selectinload(RouteStop.bus_stop),
                selectinload(BusRoute.stop_schedules).selectinload(StopSchedule.stop),
            )
        )

        with self._timer("SQL query execution"):
            result = await self.session.execute(stmt)
            routes: Sequence[BusRoute] = result.scalars().all()

        loguru.logger.debug(f"Found {len(routes)} routes containing both stops")

        journeys = []

        for route in routes:
            # Early exit: Check if route has enough active schedules
            active_schedules = [s for s in route.stop_schedules if s.is_active]
            if len(active_schedules) < 2:
                loguru.logger.debug(
                    f"Route {route.name}: insufficient active schedules ({len(active_schedules)}), skipping"
                )
                continue

            # Check if route is operational at this time (has any active schedule for today)
            has_today_schedule = any(
                getattr(schedule, current_day, True) for schedule in active_schedules
            )
            if not has_today_schedule:
                loguru.logger.debug(
                    f"Route {route.name}: no schedules for today ({current_day}), skipping"
                )
                continue

            # Get all route stops for this route, preserving order
            route_stops: list[RouteStop] = sorted(
                route.route_stops, key=lambda rs: rs.stop_order
            )

            # Find all occurrences of origin and destination stops in this route
            origin_indices = [
                (i, rs)
                for i, rs in enumerate(route_stops)
                if rs.bus_stop.name == origin_name
            ]
            destination_indices = [
                (i, rs)
                for i, rs in enumerate(route_stops)
                if rs.bus_stop.name == destination_name
            ]

            # If we don't have both stops, skip this route (though query should ensure this)
            if not origin_indices or not destination_indices:
                loguru.logger.warning(
                    f"Route {route.name}: Query returned route but missing origin/destination occurrences"
                )
                continue

            loguru.logger.debug(
                f"Processing route {route.name}: "
                f"found {len(origin_indices)} origin occurrences, "
                f"{len(destination_indices)} destination occurrences"
            )

            # Pre-filter relevant stop codes for optimization
            relevant_stop_codes = {
                rs.bus_stop.code
                for rs in route_stops
                if rs.bus_stop.name in (origin_name, destination_name)
            }

            # Group active stop schedules by trip_id (only for relevant stops)
            schedules_by_trip: dict[str, dict] = {}

            for stop_schedule in route.stop_schedules:
                if not stop_schedule.is_active:
                    continue

                # Check if this schedule is valid for today
                if not getattr(stop_schedule, current_day, True):
                    continue

                # Filter by relevant stops only
                if stop_schedule.stop.code not in relevant_stop_codes:
                    continue

                trip_id = stop_schedule.trip_id
                stop_code = stop_schedule.stop.code

                if trip_id not in schedules_by_trip:
                    schedules_by_trip[trip_id] = {}

                schedules_by_trip[trip_id][stop_code] = stop_schedule

            loguru.logger.debug(
                f"Route {route.name}: grouped {len(schedules_by_trip)} active trips for today"
            )

            # For each trip, find all valid origin->destination pairs
            trips_processed = 0
            journeys_for_route = 0

            for trip_id, trip_schedules in schedules_by_trip.items():
                trips_processed += 1
                # Consider all possible origin->destination pairs
                for orig_idx, origin_rs in origin_indices:
                    for dest_idx, dest_rs in destination_indices:
                        # Skip if destination is not after origin
                        if dest_idx <= orig_idx:
                            continue

                        # Check if we have schedules for both specific stops in this trip
                        origin_code = origin_rs.bus_stop.code
                        dest_code = dest_rs.bus_stop.code

                        if (
                            origin_code not in trip_schedules
                            or dest_code not in trip_schedules
                        ):
                            continue

                        origin_schedule = trip_schedules[origin_code]
                        dest_schedule = trip_schedules[dest_code]

                        # Filter by departure time
                        if origin_schedule.arrival_time < departure_time:
                            continue

                        # Validate timing: destination arrival must be after origin departure
                        if dest_schedule.arrival_time <= origin_schedule.arrival_time:
                            continue

                        # Calculate travel duration
                        duration = self._calculate_duration(
                            origin_schedule.arrival_time,
                            dest_schedule.arrival_time,
                        )

                        # Get the actual BusStop objects
                        origin_stop = origin_rs.bus_stop
                        destination_stop = dest_rs.bus_stop

                        segment = RouteSegment(
                            route_name=origin_schedule.route_name,
                            origin_stop=origin_stop,
                            destination_stop=destination_stop,
                            departure_time=origin_schedule.arrival_time,
                            arrival_time=dest_schedule.arrival_time,
                            travel_duration=duration,
                        )

                        journey = JourneyOption(
                            segments=[segment],
                            total_duration=duration,
                            departure_time=origin_schedule.arrival_time,
                            arrival_time=dest_schedule.arrival_time,
                            transfers=0,
                        )
                        journeys.append(journey)
                        journeys_for_route += 1

            if journeys_for_route > 0:
                loguru.logger.info(
                    f"Found {journeys_for_route} journey(s) for route {route.name} "
                    f"(processed {trips_processed} trips)"
                )

        if len(journeys) == 0:
            loguru.logger.debug("No direct journeys found")
        else:
            loguru.logger.info(f"Total: found {len(journeys)} direct journey(s)")

        # Sort by departure time, then by arrival time for same departure
        return journeys

    async def _find_routes_with_transfers(
        self,
        origin_name: str,
        destination_name: str,
        departure_time: time,
        max_results: int,
    ) -> list[JourneyOption]:
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
