"""Middleware for dependency injection of database repositories."""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import Config
from database.connection import DatabaseManager
from database.repositories import (
    BusRouteSearchRepository,
    BusRouteStopRepository,
    BusStopRepository,
    DisplayBusStopRepository,
    OrganizationCategoryRepository,
    OrganizationRepository,
)
from services.draw_route import RenderConfig, RouteDrawer
from services.route_finder import RouteFinder


class DatabaseMiddleware(BaseMiddleware):
    """
    Injects database session and repositories into handlers.

    Provides clean dependency injection pattern.
    """

    def __init__(self, db_manager: DatabaseManager, config: Config):
        """
        Initialize middleware.

        Args:
            db_manager: Database manager instance.
        """
        super().__init__()
        self.db_manager = db_manager
        self.config = config
        self.route_drawer = RouteDrawer(
            RenderConfig(buffer_ratio=0.15, pixel_size=960, dpi=250, basemap_zoom=14)
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """
        Inject dependencies into handler.

        Creates new session and repositories for each request.
        """
        async with self.db_manager.session() as session:
            # Inject repositories
            data["bus_stop_repo"] = BusStopRepository(session)
            data["bus_route_stop_repo"] = BusRouteStopRepository(session)
            data["display_bus_stop_repo"] = DisplayBusStopRepository(session)
            data["route_finder"] = RouteFinder(session)
            data["route_drawer"] = self.route_drawer
            data["bus_route_search_repo"] = BusRouteSearchRepository(session)
            data["organization_category_repo"] = OrganizationCategoryRepository(session)
            data["organization_repo"] = OrganizationRepository(session)
            data["config"] = self.config

            return await handler(event, data)
