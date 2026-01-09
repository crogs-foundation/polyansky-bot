import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot.handlers import bus_route, common, start
from bot.middlewares.database import DatabaseMiddleware
from database.connection import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log"),
    ],
)
logger = logging.getLogger(__name__)


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
    dp.update.middleware(DatabaseMiddleware(db_manager))

    # Register routers
    dp.include_router(start.router)
    dp.include_router(bus_route.router)
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
