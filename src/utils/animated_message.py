"""Utility for animating telegram messages during long-running operations."""

import asyncio
from typing import Awaitable, Callable, TypeVar

from aiogram.types import Message

T = TypeVar("T")


class AnimatedMessage:
    """Context manager for animating a telegram message while a task runs."""

    def __init__(
        self,
        message: Message,
        base_text: str,
        *,
        max_dots: int = 3,
        interval: float = 0.5,
    ):
        """
        Initialize animated message.

        Args:
            message: The telegram message to animate
            base_text: Base text to display (dots will be appended)
            max_dots: Maximum number of dots (default: 3)
            interval: Time between updates in seconds (default: 0.5)
        """
        self.message = message
        self.base_text = base_text
        self.max_dots = max_dots
        self.interval = interval
        self._task: asyncio.Task | None = None

    async def _animate(self):
        """Internal animation loop."""
        dots = 1
        while True:
            try:
                await self.message.edit_text(
                    text=self.base_text + "." * dots, parse_mode="HTML"
                )
                dots = (dots % self.max_dots) + 1
                await asyncio.sleep(self.interval)
            except Exception:
                # Message might be deleted or editing failed
                break

    async def __aenter__(self):
        """Start animation when entering context."""
        self._task = asyncio.create_task(self._animate())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop animation when exiting context."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return False


async def with_animated_message(
    message: Message,
    base_text: str,
    coro: Callable[[], Awaitable[T]],
    *,
    max_dots: int = 3,
    interval: float = 0.5,
) -> T:
    """
    Execute an async function while animating a telegram message.

    Args:
        message: The telegram message to animate
        base_text: Base text to display (dots will be appended)
        coro: Async function to execute
        max_dots: Maximum number of dots (default: 3)
        interval: Time between updates in seconds (default: 0.5)

    Returns:
        The result of the coroutine

    Example:
        result = await with_animated_message(
            message=msg,
            base_text="Генерируем карту маршрута",
            coro=lambda: route_drawer.render_route_map_png(route_name, stops)
        )
    """
    async with AnimatedMessage(message, base_text, max_dots=max_dots, interval=interval):
        return await coro()
