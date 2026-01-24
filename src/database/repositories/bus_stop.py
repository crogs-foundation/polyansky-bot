from typing import Optional

from rapidfuzz import fuzz, process
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BusStop
from database.repositories.base import BaseRepository


class BusStopRepository(BaseRepository[BusStop]):
    """Repository for bus stop CRUD and search operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(BusStop, session)

    async def get_code(self, code: str) -> BusStop | None:
        """Get record by code."""
        query = select(self.model).where(self.model.code == code)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_all(self, limit: int | None = None, offset: int = 0) -> list[BusStop]:
        """
        Get all bus stops ordered alphabetically by name.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            List of bus stops ordered by name.
        """
        query = select(self.model).order_by(BusStop.name.asc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def search_by_name(
        self, query: str, limit: int = 10, offset: int = 0
    ) -> list[BusStop]:
        """
        Fuzzy search bus stops by name using rapidfuzz.

        Handles typos, partial matches, and word variations.
        Examples:
            - "бальница" → "Центральная районная больница"
            - "вокзал" → "Железнодорожный вокзал"
            - "побед" → "улица Победы"

        Args:
            query: Search term (can contain typos).
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of matching bus stops ordered by relevance score.
        """
        if not query or not query.strip():
            return []

        query = query.strip()

        # Get all active bus stops (consider adding caching for production)
        stmt = select(BusStop).where(BusStop.is_active)
        result = await self.session.execute(stmt)
        all_stops = list(result.scalars().all())

        if not all_stops:
            return []

        # Prepare stop names for matching
        stop_names = [stop.name for stop in all_stops]

        # Use token_set_ratio for best partial word matching
        # This handles:
        # - Word order variations
        # - Partial matches
        # - Extra/missing words
        matches = process.extract(
            query,
            stop_names,
            scorer=fuzz.token_set_ratio,
            limit=len(all_stops),  # Get all stops with scores
            score_cutoff=50,  # Minimum similarity (0-100)
        )

        # Additionally, try partial_ratio for substring matching
        # This helps with cases like "бальница" → "больница"
        partial_matches = process.extract(
            query,
            stop_names,
            scorer=fuzz.partial_ratio,
            limit=len(all_stops),
            score_cutoff=60,
        )

        # Combine and deduplicate results with best scores
        combined_scores = {}
        for match_text, score, idx in matches:
            if idx not in combined_scores:
                combined_scores[idx] = score
            else:
                combined_scores[idx] = max(combined_scores[idx], score)

        for match_text, score, idx in partial_matches:
            if idx not in combined_scores:
                combined_scores[idx] = score
            else:
                # Take the best score from either method
                combined_scores[idx] = max(combined_scores[idx], score)

        # Sort by score (descending) and apply offset/limit
        sorted_indices = sorted(
            combined_scores.keys(),
            key=lambda idx: combined_scores[idx],
            reverse=True,
        )

        # Apply offset and limit
        selected_indices = sorted_indices[offset : offset + limit]

        # Return the matched stops in order of relevance
        return [all_stops[idx] for idx in selected_indices]

    async def find_nearest(
        self, latitude: float, longitude: float, limit: int = 5
    ) -> list[tuple[BusStop, float]]:
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

    async def count(self) -> int:
        results = await self.session.execute(func.count(BusStop.id))
        if results is None:
            return -1
        return results.scalar()
