"""Repository for bus stop operations."""

from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BusStop
from database.repositories.base import BaseRepository


class BusStopRepository(BaseRepository[BusStop]):
    """Repository for bus stop CRUD and search operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(BusStop, session)

    async def search_by_name(
        self, query: str, limit: int = 10, offset: int = 0
    ) -> List[BusStop]:
        """
        Search bus stops by name (case-insensitive substring match).

        Args:
            query: Search term.
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of matching bus stops ordered by relevance.
        """
        search_term = f"%{query.lower()}%"

        stmt = (
            select(BusStop)
            .where(
                or_(
                    func.lower(BusStop.name).like(search_term),
                    func.lower(BusStop.address).like(search_term),
                )
            )
            .order_by(
                # Prioritize exact name matches
                func.lower(BusStop.name) == query.lower(),
                # Then order alphabetically
                BusStop.name,
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_nearest(
        self, latitude: float, longitude: float, limit: int = 5
    ) -> List[tuple[BusStop, float]]:
        """
        Find nearest bus stops using Haversine distance.

        Args:
            latitude: Reference point latitude.
            longitude: Reference point longitude.
            limit: Maximum number of stops to return.

        Returns:
            List of (BusStop, distance_km) tuples sorted by distance.

        Note:
            Uses simplified Euclidean approximation for small distances.
            For production, consider PostGIS or more accurate calculations.
        """
        # Simplified distance calculation (good for small distances)
        # For better accuracy, use PostGIS or implement proper Haversine
        distance = func.sqrt(
            func.pow(BusStop.latitude - latitude, 2)
            + func.pow(BusStop.longitude - longitude, 2)
        )

        stmt = select(BusStop, distance.label("distance")).order_by(distance).limit(limit)

        result = await self.session.execute(stmt)
        return [
            (row[0], float(row[1]) * 111) for row in result.all()
        ]  # ~111km per degree

    async def get_by_coordinates(
        self, latitude: float, longitude: float, radius_km: float = 0.1
    ) -> Optional[BusStop]:
        """
        Find bus stop at exact coordinates within tolerance radius.

        Args:
            latitude: Target latitude.
            longitude: Target longitude.
            radius_km: Search radius in kilometers.

        Returns:
            Closest bus stop within radius or None.
        """
        stops = await self.find_nearest(latitude, longitude, limit=1)
        if stops and stops[0][1] <= radius_km:
            return stops[0][0]
        return None
