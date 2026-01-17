"""Middleware for dependency injection of database repositories."""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database.connection import DatabaseManager
from database.repositories.bus_stop import BusStopRepository
from database.repositories.display_bus_stop import DisplayBusStopRepository
from services.route_finder import RouteFinder


class DatabaseMiddleware(BaseMiddleware):
    """
    Injects database session and repositories into handlers.

    Provides clean dependency injection pattern.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize middleware.

        Args:
            db_manager: Database manager instance.
        """
        super().__init__()
        self.db_manager = db_manager

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
            data["display_bus_stop_repo"] = DisplayBusStopRepository(session)
            data["route_finder"] = RouteFinder(session)

            return await handler(event, data)
