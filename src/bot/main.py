import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from loguru import logger

from bot.config import load_config
from bot.handlers import admin, bus_route, common, organizations, start
from bot.middlewares.database import DatabaseMiddleware
from database.connection import DatabaseManager
from utils.get_path import create_path

logger.remove()

# Add console handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <cyan>{name}</cyan> - <level>{level}</level> - <level>{message}</level>",
    level="INFO",
    colorize=True  # Loguru supports colored output
)

# Add file handler
logger.add(
    create_path("logs", "bot.log"),
    format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message}",
    level="DEBUG",
    rotation="10 MB",  # Optional: rotate when file reaches 10 MB
    retention="30 days"  # Optional: keep logs for 30 days
)


async def main():
    """Initialize and start the bot."""
    # Load configuration
    config = load_config()

    # Initialize database
    db_manager = DatabaseManager(config.database.path, config.database.echo)
    await db_manager.init_database()
    logger.info(f"Database initialized at {config.database.path}")

    # Initialize bot and dispatcher
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Use memory storage for FSM (consider Redis for production)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register middlewares
    dp.update.middleware(DatabaseMiddleware(db_manager, config))

    # Register routers
    dp.include_router(admin.router)
    dp.include_router(bus_route.router)
    dp.include_router(start.router)
    dp.include_router(organizations.router)
    dp.include_router(common.router)

    logger.info("Bot started")

    try:
        # Start polling
        await dp.start_polling(bot)
    finally:
        await db_manager.close()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
