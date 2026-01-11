"""Common handlers for error handling and utility commands."""

import logging

from aiogram import F, Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, Message

from bot.keyboards.builders import build_main_menu_keyboard, build_route_menu_keyboard
from bot.keyboards.callbacks import RouteAction, RouteMenuCallback
from bot.states.bus_route import BusRouteStates

router = Router(name="common")
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """
    Handle cancel callback from inline keyboards.

    Returns user to main menu and clears state.
    """
    await state.clear()

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "❌ Действие отменено.", reply_markup=build_main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(RouteMenuCallback.filter(F.action == RouteAction.BACK))  # FIXED
async def callback_back(callback: CallbackQuery, state: FSMContext):
    """
    Handle back navigation from inline keyboards.

    Returns to route planning menu if in appropriate state.
    """
    current_state = await state.get_state()

    # If in route planning workflow, return to menu
    if current_state and "BusRouteStates" in current_state:
        await state.set_state(BusRouteStates.menu)
        data = await state.get_data()

        await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
            "🚌 <b>Планирование маршрута</b>\n\nВыберите параметры вашей поездки:",
            reply_markup=build_route_menu_keyboard(
                origin=data.get("origin_name"),
                destination=data.get("destination_name"),
                departure=data.get("departure_time", "Сейчас"),
                arrival=data.get("arrival_time", "Как можно скорее"),
            ),
            parse_mode="HTML",
        )
    else:
        # Otherwise go to main menu
        await state.clear()
        await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
            "Главное меню:", reply_markup=build_main_menu_keyboard()
        )

    await callback.answer()


@router.callback_query(F.data == "page_info")
async def callback_page_info(callback: CallbackQuery):
    """
    Handle pagination info button (non-clickable).

    Just shows a notification.
    """
    await callback.answer(
        "ℹ️ Это индикатор страницы. Используйте стрелки для навигации.", show_alert=False
    )


@router.message(BusRouteStates.waiting_departure_time)
@router.message(BusRouteStates.waiting_arrival_time)
async def invalid_time_format(message: Message):
    """
    Handle invalid time format input.

    Triggered when user enters time in wrong format.
    """
    await message.answer(
        "❌ <b>Неверный формат времени</b>\n\n"
        "Пожалуйста, используйте формат <b>ЧЧ:ММ</b>\n\n"
        "Примеры:\n"
        "• <code>09:30</code>\n"
        "• <code>14:15</code>\n"
        "• <code>23:59</code>\n\n"
        "Или используйте /cancel для отмены.",
        parse_mode="HTML",
    )


@router.message(
    BusRouteStates.waiting_origin_location,
    BusRouteStates.waiting_destination_location,
    ~F.location,
)
async def invalid_location_input(message: Message):
    """
    Handle invalid input when expecting location.

    Reminds user to send actual location.
    """
    await message.answer(
        "❌ <b>Ожидается геолокация</b>\n\n"
        "Пожалуйста, отправьте геолокацию с помощью кнопки 📎 → Геолокация\n\n"
        "Или используйте /cancel для отмены.",
        parse_mode="HTML",
    )


@router.message(
    BusRouteStates.waiting_origin_search,
    BusRouteStates.waiting_destination_search,
    ~F.text,
)
async def invalid_search_input(message: Message):
    """
    Handle invalid input when expecting text search query.
    """
    await message.answer(
        "❌ <b>Ожидается текст</b>\n\n"
        "Пожалуйста, введите название остановки текстом.\n\n"
        "Или используйте /cancel для отмены.",
        parse_mode="HTML",
    )


@router.message(F.text)
async def unexpected_message(message: Message, state: FSMContext):
    """
    Handle unexpected text messages.

    Provides helpful guidance to lost users.
    """
    current_state = await state.get_state()

    if current_state is None:
        # User not in any conversation flow
        await message.answer(
            "🤔 Я не понимаю эту команду.\n\n"
            "Используйте /start для начала работы или /help для справки.",
            reply_markup=build_main_menu_keyboard(),
        )
    else:
        # User in conversation but sent wrong input
        await message.answer(
            "🤔 Не понимаю, что вы имеете в виду.\n\n"
            "Пожалуйста, используйте кнопки меню или отправьте /cancel для отмены."
        )


@router.error(ExceptionTypeFilter(Exception))
async def error_handler(event: ErrorEvent):
    """
    Global error handler.

    Logs errors and provides user-friendly messages.
    Prevents bot from crashing on unexpected errors.
    """
    logger.exception(
        "An error occurred during update processing",
        exc_info=event.exception,
        extra={
            "update": event.update.model_dump() if event.update else None,
        },
    )

    # Try to notify user about the error
    try:
        if event.update.message:
            await event.update.message.answer(
                "😞 <b>Произошла ошибка</b>\n\n"
                "Пожалуйста, попробуйте ещё раз или используйте /cancel.\n\n"
                "Если проблема повторяется, обратитесь к администратору.",
                parse_mode="HTML",
            )
        elif event.update.callback_query:
            await event.update.callback_query.message.answer(  # ty: ignore [possibly-missing-attribute]
                "😞 <b>Произошла ошибка</b>\n\n"
                "Пожалуйста, попробуйте ещё раз или используйте /cancel.",
                parse_mode="HTML",
            )
            await event.update.callback_query.answer(
                "Произошла ошибка при обработке запроса", show_alert=True
            )
    except Exception as e:
        logger.exception("Failed to send error message to user", exc_info=e)

    # Return True to prevent error from propagating
    return True


@router.callback_query()
async def unknown_callback(callback: CallbackQuery):
    """
    Handle unknown/outdated callback queries.

    Prevents errors from old inline keyboards.
    """
    logger.warning(
        f"Unknown callback received: {callback.data} from user {callback.from_user.id}"
    )

    await callback.answer(
        "⚠️ Эта кнопка устарела. Пожалуйста, начните заново с /start", show_alert=True
    )
