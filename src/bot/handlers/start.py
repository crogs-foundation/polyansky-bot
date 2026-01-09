"""Handlers for bot initialization and main menu."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.builders import build_main_menu_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    Handle /start command.

    Displays welcome message and main menu.
    Clears any existing FSM state.
    """
    # Clear any previous conversation state
    await state.clear()

    user_name = message.from_user.first_name or "пользователь"

    welcome_text = (
        f"👋 Привет, <b>{user_name}</b>!\n\n"
        f"Я помогу вам найти оптимальный маршрут на автобусе "
        f"в городе Вятские Поляны.\n\n"
        f"<b>Что я умею:</b>\n"
        f"🚌 Поиск маршрутов между остановками\n"
        f"📍 Поиск ближайших остановок\n"
        f"🕐 Расчёт времени в пути\n"
        f"🗺 Показ остановок на карте\n\n"
        f"Нажмите кнопку ниже, чтобы начать!"
    )

    # Create inline keyboard with "Автобусы" button
    keyboard = build_main_menu_keyboard()

    await message.answer(text=welcome_text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Handle /help command.

    Shows detailed usage instructions.
    """
    help_text = (
        "📖 <b>Справка по использованию бота</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
        "/cancel - Отменить текущее действие\n\n"
        "<b>Как найти маршрут:</b>\n"
        '1️⃣ Нажмите кнопку <b>"Автобусы"</b>\n'
        "2️⃣ Укажите начальную и конечную остановки:\n"
        "   • 📍 На карте - отправьте геолокацию\n"
        "   • 📋 Из списка - выберите из всех остановок\n"
        "   • 🔍 Поиском - введите название\n"
        "3️⃣ Укажите время отправления (опционально)\n"
        '4️⃣ Нажмите <b>"Подтвердить"</b>\n\n'
        "<b>Полезные советы:</b>\n"
        "💡 Используйте поиск для быстрого нахождения остановки\n"
        "💡 Отправьте геолокацию для автоматического выбора ближайшей остановки\n"
        "💡 Бот покажет несколько вариантов маршрута - выберите удобный\n\n"
        "❓ <b>Возникли проблемы?</b>\n"
        "Используйте /cancel для отмены текущей операции и возврата в главное меню."
    )

    await message.answer(text=help_text, parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """
    Handle /cancel command.

    Clears FSM state and returns to main menu.
    """
    current_state = await state.get_state()

    if current_state is None:
        await message.answer(
            "Нечего отменять. Вы в главном меню.\n\nИспользуйте /start для начала работы."
        )
        return

    await state.clear()

    await message.answer(
        "✅ Действие отменено. Возвращаемся в главное меню.",
        reply_markup=build_main_menu_keyboard(),
    )
