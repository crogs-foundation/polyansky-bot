"""Inline keyboard factory functions."""

from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from bot.keyboards.callbacks import (
    InputMethod,
    InputMethodCallback,
    ListNavigationCallback,
    RouteAction,
    RouteChooseCallback,
    RouteMenuCallback,
    StopListCallback,
    TimePresetCallback,
)
from database.models import DisplayBusStop
from services.route_finder import JourneyOption


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build main menu keyboard with 'Автобусы' button."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🚌 Автобусы",
        callback_data=RouteMenuCallback(action=RouteAction.START_BUSES),
    )
    return builder.as_markup()


def build_route_menu_keyboard(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    departure: str | None = None,
    arrival: str | None = None,
) -> InlineKeyboardMarkup:
    """
    Build route planning menu with current values.

    Creates 4-row table layout with labels and values.
    Entire row is clickable for editing.

    Args:
        origin: Origin stop name or "Не указано".
        destination: Destination stop name or "Не указано".
        departure: Departure time string.
        arrival: Arrival time string.

    Returns:
        Inline keyboard markup.
    """
    if not departure:
        departure = "Сейчас"
    if not arrival:
        arrival = "Как можно скорее"
    origin_text = origin or "Не указано"
    destination_text = destination or "Не указано"

    builder = InlineKeyboardBuilder()

    # Row 1: Origin (Откуда)
    builder.button(
        text=f"📍 Откуда: {origin_text}",
        callback_data=RouteMenuCallback(action=RouteAction.EDIT_ORIGIN),
    )
    builder.adjust(1)

    # Row 2: Destination (Куда)
    builder.button(
        text=f"📍 Куда: {destination_text}",
        callback_data=RouteMenuCallback(action=RouteAction.EDIT_DESTINATION),
    )
    builder.adjust(1)

    # Row 3: Departure time
    builder.button(
        text=f"🕐 Отправление: {departure}",
        callback_data=RouteMenuCallback(action=RouteAction.EDIT_DEPARTURE),
    )
    builder.adjust(1)

    # Row 4: Arrival time
    builder.button(
        text=f"🕐 Прибытие: {arrival}",
        callback_data=RouteMenuCallback(action=RouteAction.EDIT_ARRIVAL),
    )
    builder.adjust(1)

    # Row 5: Action buttons
    builder.button(
        text="❌ Отмена",
        callback_data=RouteMenuCallback(action=RouteAction.CANCEL),
    )
    builder.button(
        text="✅ Подтвердить",
        callback_data=RouteMenuCallback(action=RouteAction.CONFIRM),
    )
    builder.adjust(2)

    return builder.as_markup()


def build_input_method_keyboard(field: str) -> InlineKeyboardMarkup:
    """
    Build keyboard for selecting input method.

    Args:
        field: 'origin' or 'destination'.

    Returns:
        Keyboard with 3 input method options.
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="📍 Указать на карте",
        callback_data=InputMethodCallback(field=field, method=InputMethod.LOCATION),
    )
    builder.button(
        text="📋 Выбрать из списка",
        callback_data=InputMethodCallback(field=field, method=InputMethod.LIST),
    )
    builder.button(
        text="🔍 Найти по названию",
        callback_data=InputMethodCallback(field=field, method=InputMethod.SEARCH),
    )
    builder.button(
        text="« Назад",
        callback_data=RouteMenuCallback(action=RouteAction.BACK),  # FIXED
    )

    builder.adjust(1)
    return builder.as_markup()


def build_stop_list_keyboard(
    stops: List[DisplayBusStop], field: str, page: int = 0, total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Build paginated list of bus stops.

    Shows max 5 stops per page with navigation buttons.

    Args:
        stops: List of bus stops to display (max 5).
        field: 'origin' or 'destination'.
        page: Current page number (0-indexed).
        total_pages: Total number of pages.

    Returns:
        Keyboard with stop buttons and navigation.
    """
    builder = InlineKeyboardBuilder()

    stop_names = list(sorted(set(stop.name for stop in stops)))

    # Add stop buttons - one button per row using row() method
    for name in stop_names[:5]:
        builder.row(
            InlineKeyboardButton(
                text=f"{name}",
                callback_data=StopListCallback(stop_name=name, field=field).pack(),
            )
        )

    # Build navigation buttons list
    nav_buttons = []

    enabled_back = page > 0
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"{'◀️' if enabled_back else '✖️'} Назад",
            callback_data=ListNavigationCallback(page=page - 1, field=field).pack()
            if enabled_back
            else "disabled_back",
        )
    )

    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="page_info")
    )

    enabled_forward = page < total_pages - 1
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"Вперёд {'▶️' if enabled_forward else '✖️'}",
            callback_data=ListNavigationCallback(page=page + 1, field=field).pack()
            if enabled_forward
            else "disabled_forward",
        )
    )

    # Add all navigation buttons as a single row
    builder.row(*nav_buttons)

    # Add Back button as a separate row
    builder.row(
        InlineKeyboardButton(
            text="« Назад",
            callback_data=RouteMenuCallback(action=RouteAction.BACK).pack(),
        )
    )

    return builder.as_markup()


def build_time_preset_keyboard(field: str) -> InlineKeyboardMarkup:
    """
    Build keyboard for time selection.

    Offers presets and custom input option.

    Args:
        field: 'departure' or 'arrival'.

    Returns:
        Keyboard with time options.
    """
    builder = InlineKeyboardBuilder()

    if field == "departure":
        builder.button(
            text="🕐 Сейчас",
            callback_data=TimePresetCallback(field=field, preset="now"),
        )
        builder.button(
            text="⌨️ Указать время",
            callback_data=TimePresetCallback(field=field, preset="custom"),
        )
    else:  # arrival
        builder.button(
            text="⚡ Как можно скорее",
            callback_data=TimePresetCallback(field=field, preset="asap"),
        )
        builder.button(
            text="⌨️ Указать время",
            callback_data=TimePresetCallback(field=field, preset="custom"),
        )

    builder.button(
        text="« Назад",
        callback_data=RouteMenuCallback(action=RouteAction.BACK),  # FIXED
    )
    builder.adjust(1)

    return builder.as_markup()


def build_choose_route_keyboard(routes: list[JourneyOption]) -> InlineKeyboardMarkup:
    """
    Build keyboard for time selection.

    Offers presets and custom input option.

    Args:
        field: 'departure' or 'arrival'.

    Returns:
        Keyboard with time options.
    """
    builder = InlineKeyboardBuilder()

    index = 0

    for route in routes:
        for segment in route.segments:
            index += 1
            arrival_time = segment.arrival_time.isoformat("minutes").replace(":", "-")
            departure_time = segment.departure_time.isoformat("minutes").replace(":", "-")
            logger.info(arrival_time)
            logger.info(departure_time)
            builder.row(
                InlineKeyboardButton(
                    text=f"{index}. Маршрут {segment.route_name}",
                    callback_data=RouteChooseCallback(
                        index=index,
                        route_name=segment.route_name,
                        origin_stop=segment.origin_stop.code,
                        destination_stop=segment.destination_stop.code,
                        arrival_time=arrival_time,
                        departure_time=departure_time,
                        travel_duration=int(segment.travel_duration.total_seconds() / 60),
                    ).pack(),
                )
            )

    return builder.as_markup()
