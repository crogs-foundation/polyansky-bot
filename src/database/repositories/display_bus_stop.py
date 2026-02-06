import loguru

from rapidfuzz import fuzz, process
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DisplayBusStop
from database.repositories.base import BaseRepository

logger = loguru.logger.bind(name=__name__)

class DisplayBusStopRepository(BaseRepository[DisplayBusStop]):
    """Repository for bus stop CRUD and search operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(DisplayBusStop, session)

    async def get_name_exact(self, name: str) -> DisplayBusStop | None:
        return (
            (
                await self.session.execute(
                    select(DisplayBusStop).where(DisplayBusStop.name == name)
                )
            )
            .scalars()
            .first()
        )

    async def get_all(
        self, limit: int | None = None, offset: int = 0
    ) -> list[DisplayBusStop]:
        """
        Get all bus stops ordered alphabetically by name.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            List of bus stops ordered by name.
        """
        logger.debug(f"{limit=}, {offset=}")
        query = select(self.model).order_by(DisplayBusStop.name.asc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)

        result = await self.session.execute(query)
        results = list(result.scalars().all())

        logger.debug(f"{results=}")
        if len(results) == 0:
            logger.warning("Found 0 bus stops in database")

        return results

    async def search_by_name(
        self, query: str, limit: int = 10, offset: int = 0
    ) -> list[DisplayBusStop]:
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
        all_stops: list[DisplayBusStop] = list(
            (await self.session.execute(select(DisplayBusStop))).scalars().all()
        )

        if not all_stops:
            return []

        # Prepare stop names for matching
        stop_searches: list[str] = [stop.search for stop in all_stops]

        # Use token_set_ratio for best partial word matching
        # This handles:
        # - Word order variations
        # - Partial matches
        # - Extra/missing words
        matches = process.extract(
            query,
            stop_searches,
            scorer=fuzz.token_set_ratio,
            limit=len(all_stops),  # Get all stops with scores
            score_cutoff=50,  # Minimum similarity (0-100)
        )

        # Additionally, try partial_ratio for substring matching
        # This helps with cases like "бальница" → "больница"
        partial_matches = process.extract(
            query,
            stop_searches,
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

    async def count(self) -> int:
        results = await self.session.execute(func.count(DisplayBusStop.name))
        if results is None:
            return -1
        return results.scalar()
