"""Handlers for bot initialization and main menu."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.config import Config
from bot.keyboards.builders import build_main_menu_keyboard
from bot.keyboards.callbacks import (
    AdminAction,
    AdminCallback,
    RouteAction,
    RouteMenuCallback,
)

router = Router(name="start")


def make_message(
    username: str, is_admin: bool | None = False
) -> tuple[str, InlineKeyboardMarkup]:
    welcome_text = (
        f"👋 Привет, <b>{username}</b>!\n\n"
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
    keyboard = build_main_menu_keyboard(is_admin=not not is_admin)

    return welcome_text, keyboard


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, config: Config):
    """
    Handle /start command.

    Displays welcome message and main menu.
    Clears any existing FSM state.
    """
    if not message.from_user:
        return ValueError  # TODO: handle exception

    # Clear any previous conversation state
    await state.clear()

    username = message.from_user.first_name or "пользователь"
    admin_ids = config.bot.admin_ids  # Извлечь admin_ids из конфига
    is_admin = message.from_user.id in admin_ids

    welcome_text, keyboard = make_message(username, is_admin)

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


@router.callback_query(RouteMenuCallback.filter(F.action == RouteAction.MAIN_MENU))
async def callback_main_menu(callback: CallbackQuery, state: FSMContext, config: Config):
    """
    Handle main menu navigation from callback.

    Shows the same main menu as /start command.
    """
    if not callback.from_user:
        return

    # Clear any previous conversation state
    await state.clear()

    username = callback.from_user.first_name or "пользователь"
    admin_ids = config.bot.admin_ids  # Извлечь admin_ids из конфига
    is_admin = callback.from_user.id in admin_ids

    welcome_text, keyboard = make_message(username, is_admin)

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        text=welcome_text, reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


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


@router.callback_query(AdminCallback.filter(F.action == AdminAction.CANCEL))
async def cancel_admin_action(
    callback: CallbackQuery,
    state: FSMContext,
    config: Config,
    callback_data: AdminCallback,
):
    """Cancel admin action and return to main menu."""
    await state.clear()

    username = callback.from_user.first_name or "пользователь"
    admin_ids = config.bot.admin_ids  # Извлечь admin_ids из конфига
    is_admin = callback.from_user.id in admin_ids

    welcome_text, keyboard = make_message(username, is_admin)

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        text=welcome_text, reply_markup=build_main_menu_keyboard(is_admin=is_admin)
    )
    await callback.answer()
