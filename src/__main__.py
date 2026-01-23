import asyncio
from os import environ

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = environ.get("TELEGRAM_TOKEN")


async def main():
    if TOKEN is None:
        raise EnvironmentError("`TELEGRAM_TOKEN` was not specified")
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()

    dp = Dispatcher(storage=storage)

    dp.message.filter(F.chat.type == "private")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
