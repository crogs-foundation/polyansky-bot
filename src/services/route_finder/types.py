from dataclasses import dataclass
from datetime import time, timedelta
from typing import Any, Self

from database.models import BusStop


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

    def __eq__(self, other: Any) -> bool:
        """Check if two journeys are equal."""
        if not isinstance(other, JourneyOption):
            return False
        return self.get_key() == other.get_key()

    def __hash__(self) -> int:
        """Make JourneyOption hashable for set operations."""
        return hash(self.get_key())
