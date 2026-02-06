"""Handlers for bus route planning workflow."""

from datetime import datetime

import loguru
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InputMediaPhoto,
    Location,
    Message,
)

from bot.keyboards.builders import (
    build_choose_route_keyboard,
    build_input_method_keyboard,
    build_route_menu_keyboard,
    build_stop_list_keyboard,
    build_time_preset_keyboard,
)
from bot.keyboards.callbacks import (
    InputMethodCallback,
    ListNavigationCallback,
    RouteAction,
    RouteChooseCallback,
    RouteMenuCallback,
    StopListCallback,
    TimePresetCallback,
)
from bot.states.bus_route import BusRouteStates
from database.repositories import (
    BusRouteSearchRepository,
    BusRouteStopRepository,
    BusStopRepository,
    DisplayBusStopRepository,
)
from services.draw_route import RouteDrawer
from services.route_finder import JourneyOption, RouteFinder
from utils.animated_message import AnimatedMessage

router = Router(name="bus_route")

logger = loguru.logger.bind(name=__name__)

# Constants
STOPS_PER_PAGE = 5


@router.callback_query(RouteMenuCallback.filter(F.action == RouteAction.START_BUSES))
async def show_route_menu(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: RouteMenuCallback,
    bus_route_search_repo: BusRouteSearchRepository,
):
    """
    Show initial route planning menu.

    Triggered by "Автобусы" button from main menu.
    """
    await state.set_state(BusRouteStates.menu)

    search = await bus_route_search_repo.last(callback.from_user.id)
    logger.debug(f"Last search of user {callback.from_user.id} is: {search}")

    origin = search.origin if search else None
    destination = search.destination if search else None
    # Initialize FSM data
    await state.update_data(
        origin_name=origin,
        destination_name=destination,
        departure_time="Сейчас",
        arrival_time="Как можно скорее",
    )

    text = "🚌 <b>Планирование маршрута</b>\n\nВыберите параметры вашей поездки:"

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        text=text,
        reply_markup=build_route_menu_keyboard(origin=origin, destination=destination),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    RouteMenuCallback.filter(F.action == RouteAction.EDIT_ORIGIN),
    StateFilter(BusRouteStates.menu),
)
async def edit_origin(
    callback: CallbackQuery, state: FSMContext, callback_data: RouteMenuCallback
):
    """Show input method selection for origin."""
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "📍 <b>Выберите способ указания начальной точки:</b>",
        reply_markup=build_input_method_keyboard("origin"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    RouteMenuCallback.filter(F.action == RouteAction.EDIT_DESTINATION),
    StateFilter(BusRouteStates.menu),
)
async def edit_destination(
    callback: CallbackQuery, state: FSMContext, callback_data: RouteMenuCallback
):
    """Show input method selection for destination."""
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "📍 <b>Выберите способ указания конечной точки:</b>",
        reply_markup=build_input_method_keyboard("destination"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(InputMethodCallback.filter(F.method == "location"))
async def request_location(
    callback: CallbackQuery, state: FSMContext, callback_data: InputMethodCallback
):
    """Request user to send location."""
    field = callback_data.field

    if field == "origin":
        await state.set_state(BusRouteStates.waiting_origin_location)
        text = "📍 Отправьте геолокацию начальной точки"
    else:
        await state.set_state(BusRouteStates.waiting_destination_location)
        text = "📍 Отправьте геолокацию конечной точки"

    # Delete the menu message
    await callback.message.delete()  # ty: ignore [possibly-missing-attribute]

    # Send new message requesting location
    await callback.message.answer(f"{text}\n\nИспользуйте кнопку 📎 → Геолокация")  # ty: ignore [possibly-missing-attribute]
    await callback.answer()


@router.message(
    StateFilter(
        BusRouteStates.waiting_origin_location,
        BusRouteStates.waiting_destination_location,
    ),
    F.location,
)
async def process_location(
    message: Message, state: FSMContext, bus_stop_repo: BusStopRepository
):
    """
    Process received location and find nearest bus stop.

    Injected dependencies: bus_stop_repo via middleware.
    """
    if message.location is None:
        raise ValueError  # TODO: handle exception
    location: Location = message.location
    current_state = await state.get_state()

    # Find nearest stop
    stops_with_distance = await bus_stop_repo.find_nearest(
        location.latitude, location.longitude, limit=1
    )

    if not stops_with_distance:
        await message.answer(
            "❌ Не найдено остановок поблизости. Попробуйте другой способ выбора."
        )
        return

    stop, distance = stops_with_distance[0]

    # Update state data
    field = "origin" if current_state and "origin" in current_state else "destination"
    await state.update_data(**{f"{field}_name": stop.name})

    # Return to menu
    await state.set_state(BusRouteStates.menu)
    data = await state.get_data()

    await message.delete()
    await message.answer(
        f"✅ Выбрана остановка: <b>{stop.name}</b>\n📏 Расстояние: {distance:.2f} км",
        reply_markup=build_route_menu_keyboard(
            origin=data.get("origin_name"),
            destination=data.get("destination_name"),
            departure=data.get("departure_time"),
            arrival=data.get("arrival_time"),
        ),
        parse_mode="HTML",
    )


@router.callback_query(InputMethodCallback.filter(F.method == "list"))
async def show_stop_list(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: InputMethodCallback,
    display_bus_stop_repo: DisplayBusStopRepository,
):
    """Show paginated list of all bus stops."""
    field = callback_data.field
    # Set appropriate state
    if field == "origin":
        await state.set_state(BusRouteStates.waiting_origin_list)
    else:
        await state.set_state(BusRouteStates.waiting_destination_list)

    # Get first page of stops
    total_count = await display_bus_stop_repo.count()
    total_pages = (total_count + STOPS_PER_PAGE - 1) // STOPS_PER_PAGE
    stops = await display_bus_stop_repo.get_all(limit=STOPS_PER_PAGE, offset=0)

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        f"📋 <b>Выберите остановку:</b>\n\nСтраница 1 из {total_pages}",
        reply_markup=build_stop_list_keyboard(
            stops, field, page=0, total_pages=total_pages
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(StopListCallback.filter())
async def select_stop_from_list(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: StopListCallback,
    display_bus_stop_repo: DisplayBusStopRepository,
):
    """Handle bus stop selection from list."""
    stop = await display_bus_stop_repo.get_name_exact(callback_data.stop_name)
    field = callback_data.field

    if not stop:
        await callback.answer("❌ Остановка не найдена", show_alert=True)
        return

    # Update state
    await state.update_data({f"{field}_name": stop.name})
    await state.set_state(BusRouteStates.menu)

    # Return to menu
    data = await state.get_data()
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        f"✅ Выбрана остановка: <b>{stop.name}</b>",
        reply_markup=build_route_menu_keyboard(
            origin=data.get("origin_name"),
            destination=data.get("destination_name"),
            departure=data.get("departure_time"),
            arrival=data.get("arrival_time"),
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(InputMethodCallback.filter(F.method == "search"))
async def request_search_query(
    callback: CallbackQuery, state: FSMContext, callback_data: InputMethodCallback
):
    """Request user to type search query."""
    field = callback_data.field

    if field == "origin":
        await state.set_state(BusRouteStates.waiting_origin_search)
        text = "🔍 Введите название начальной остановки:"
    else:
        await state.set_state(BusRouteStates.waiting_destination_search)
        text = "🔍 Введите название конечной остановки:"

    await callback.message.edit_text(text)  # ty: ignore [possibly-missing-attribute]
    await callback.answer()


@router.message(
    StateFilter(
        BusRouteStates.waiting_origin_search,
        BusRouteStates.waiting_destination_search,
    ),
    F.text,
)
async def process_search_query(
    message: Message, state: FSMContext, display_bus_stop_repo: DisplayBusStopRepository
):
    """Search bus stops by user query and show results."""
    if message.text is None:
        raise ValueError  # TODO: handle exception

    query = message.text.strip()
    current_state = await state.get_state()

    field = "origin" if current_state and "origin" in current_state else "destination"

    # Search stops
    stops = await display_bus_stop_repo.search_by_name(query, limit=STOPS_PER_PAGE)

    if not stops:
        await message.answer(
            f"❌ Не найдено остановок по запросу '<b>{query}</b>'\n\n"
            f"Попробуйте другой запрос или выберите другой способ.",
            parse_mode="HTML",
        )
        return

    # Show results as list
    total_pages = 1  # Only show first page of search results
    await message.answer(
        f"🔍 Результаты поиска по запросу '<b>{query}</b>':",
        reply_markup=build_stop_list_keyboard(
            stops, field, page=0, total_pages=total_pages
        ),
        parse_mode="HTML",
    )


@router.callback_query(
    RouteMenuCallback.filter(F.action == RouteAction.EDIT_DEPARTURE),
    StateFilter(BusRouteStates.menu),
)
async def edit_departure_time(
    callback: CallbackQuery, state: FSMContext, callback_data: RouteMenuCallback
):
    """Show departure time options."""
    await state.set_state(BusRouteStates.waiting_departure_time)
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "🕐 <b>Время отправления:</b>",
        reply_markup=build_time_preset_keyboard("departure"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    RouteMenuCallback.filter(F.action == RouteAction.EDIT_ARRIVAL),
    StateFilter(BusRouteStates.menu),
)
async def edit_arrival_time(
    callback: CallbackQuery, state: FSMContext, callback_data: RouteMenuCallback
):
    """Show arrival time options."""
    await state.set_state(BusRouteStates.waiting_arrival_time)
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "🕐 <b>Время прибытия:</b>",
        reply_markup=build_time_preset_keyboard("arrival"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(TimePresetCallback.filter(F.preset != "custom"))
async def set_time_preset(
    callback: CallbackQuery, state: FSMContext, callback_data: TimePresetCallback
):
    """Set preset time value."""
    field = callback_data.field
    preset = callback_data.preset

    if preset == "now":
        value = "Сейчас"
    elif preset == "asap":
        value = "Как можно скорее"
    else:
        value = preset

    await state.update_data({f"{field}_time": value})
    await state.set_state(BusRouteStates.menu)

    # Return to menu
    data = await state.get_data()
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "✅ Время обновлено",
        reply_markup=build_route_menu_keyboard(
            origin=data.get("origin_name"),
            destination=data.get("destination_name"),
            departure=data.get("departure_time"),
            arrival=data.get("arrival_time"),
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(TimePresetCallback.filter(F.preset == "custom"))
async def request_custom_time(
    callback: CallbackQuery, state: FSMContext, callback_data: TimePresetCallback
):
    """Request custom time input."""
    field = callback_data.field
    await state.update_data(time_field=field)

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "⌨️ Введите время в формате <b>ЧЧ:ММ</b>\n\n"
        "Например: <code>14:30</code> или <code>9:05</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(
    StateFilter(
        BusRouteStates.waiting_departure_time, BusRouteStates.waiting_arrival_time
    ),
    F.text.regexp(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"),
)
async def process_custom_time(message: Message, state: FSMContext):
    """Process custom time input."""
    if message.text is None:
        raise ValueError  # TODO: handle exception

    time_str = message.text.strip()
    data = await state.get_data()
    field = data.get("time_field", "departure")

    await state.update_data({f"{field}_time": time_str})
    await state.set_state(BusRouteStates.menu)

    data = await state.get_data()
    await message.answer(
        f"✅ Время установлено: <b>{time_str}</b>",
        reply_markup=build_route_menu_keyboard(
            origin=data.get("origin_name"),
            destination=data.get("destination_name"),
            departure=data.get("departure_time"),
            arrival=data.get("arrival_time"),
        ),
        parse_mode="HTML",
    )


@router.callback_query(
    RouteMenuCallback.filter(F.action == RouteAction.CONFIRM),
    StateFilter(BusRouteStates.menu),
)
async def confirm_route(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: RouteMenuCallback,
    route_finder: RouteFinder,
    bus_stop_repo: BusStopRepository,
    bus_route_search_repo: BusRouteSearchRepository,
):
    """
    Confirm route selection and find available routes.

    Validates input and displays route options.
    """
    data = await state.get_data()

    # Validate required fields
    if not data.get("origin_name") or not data.get("destination_name"):
        await callback.answer(
            "❌ Укажите начальную и конечную остановки", show_alert=True
        )
        return

    # Parse departure time
    departure_str = data.get("departure_time", "Сейчас")
    departure_time = None
    if departure_str != "Сейчас":
        try:
            hour, minute = map(int, departure_str.split(":"))
            departure_time = datetime.now().replace(hour=hour, minute=minute).time()
        except ValueError:
            pass

    # Find routes
    await callback.answer("🔍 Ищем маршруты...", show_alert=False)

    try:
        routes: list[JourneyOption] = await route_finder.find_routes(
            origin_name=data["origin_name"],
            destination_name=data["destination_name"],
            departure_time=departure_time,
            max_results=3,
        )

        await bus_route_search_repo.create(
            origin=data["origin_name"],
            destination=data["destination_name"],
            telegram_user_id=callback.from_user.id,
        )

        if not routes:
            await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
                "❌ <b>Маршруты не найдены</b>\n\nПопробуйте изменить параметры поиска.",
                parse_mode="HTML",
            )
            return

        # Format results
        result_text = "🚌 <b>Найденные маршруты:</b>\n\n"
        for idx, route in enumerate(routes, 1):
            result_text += f"<b>Вариант {idx}:</b>\n"
            for segment in route.segments:
                result_text += (
                    f"🚌 Маршрут {segment.route_name}\n"
                    f"📍 {segment.origin_stop.name}\n\n"
                    f"🕐 Отправление: {segment.departure_time.strftime('%H:%M')}\n"
                    f"📍 {segment.destination_stop.name}\n"
                    f"🕐 Прибытие: {segment.arrival_time.strftime('%H:%M')}\n\n"
                )
            result_text += f"✅ Всего: {route.total_duration}\n"
            result_text += "━━━━━━━━━━━━━━\n\n"

        await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
            result_text,
            reply_markup=build_choose_route_keyboard(routes),
            parse_mode="HTML",
        )

    except Exception as e:
        await callback.message.edit_text("❌ Ошибка при поиске маршрутов.")  # ty: ignore [possibly-missing-attribute]
        logger.error(f"❌ Ошибка при поиске маршрутов: {str(e)}")


@router.callback_query(RouteChooseCallback.filter())
async def choose_route(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: RouteChooseCallback,
    route_finder: RouteFinder,
    route_drawer: RouteDrawer,
    bus_stop_repo: BusStopRepository,
    bus_route_stop_repo: BusRouteStopRepository,
):
    await callback.answer()

    route_name = callback_data.route_name
    origin_stop = callback_data.origin_stop
    destination_stop = callback_data.destination_stop
    departure_time = callback_data.departure_time.replace("-", ":")
    arrival_time = callback_data.arrival_time.replace("-", ":")
    travel_duration = callback_data.travel_duration

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        text=(
            "Ваш маршрут:"
            f"🚌 Маршрут {route_name}\n"
            f"📍 {origin_stop}\n\n"
            f"🕐 Отправление:  {departure_time}\n"
            f"📍 {destination_stop}\n\n"
            f"🕐 Прибытие: {arrival_time}\n\n"
            f"Время в пути: {travel_duration} минут."
        ),
        parse_mode="HTML",
    )

    last_message = await callback.message.answer(  # ty: ignore [possibly-missing-attribute]
        text="Генерируем карту маршрута", parse_mode="HTML"
    )

    async with AnimatedMessage(last_message, "Генерируем карту маршрута"):
        stops = await bus_route_stop_repo.get_stops(
            route_name, origin_stop, destination_stop
        )
        logger.debug(f"{stops=}")
        route_map = await route_drawer.render_route_map_png(
            route_name,
            stops=list(
                map(lambda item: (item.latitude, item.longitude, item.name), stops)
            ),
        )

    file = BufferedInputFile(
        route_map,
        filename=f"Map of route `{route_name}` from `{stops[0].name}` to `{stops[-1].name}`.png",
    )

    await last_message.edit_media(InputMediaPhoto(media=file))
    await state.clear()


@router.callback_query(
    RouteMenuCallback.filter(F.action == RouteAction.CANCEL),
    StateFilter("*"),
)
async def cancel_route_planning(
    callback: CallbackQuery, state: FSMContext, callback_data: RouteMenuCallback
):
    """Cancel route planning and return to main menu."""
    await state.clear()
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "Планирование маршрута отменено.",
        reply_markup=None,
    )
    await callback.answer()
    await callback.answer()


@router.callback_query(ListNavigationCallback.filter())
async def navigate_stop_list(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: ListNavigationCallback,
    display_bus_stop_repo: DisplayBusStopRepository,
):
    """
    Handle pagination navigation in bus stop list.

    Updates the message to show the requested page of stops.
    """
    page = callback_data.page
    field = callback_data.field

    # Get total count for pagination calculation
    total_count = await display_bus_stop_repo.count()
    total_pages = (total_count + STOPS_PER_PAGE - 1) // STOPS_PER_PAGE

    # Validate page bounds
    if page < 0 or page >= total_pages:
        await callback.answer("❌ Недопустимая страница", show_alert=True)
        return

    # Fetch stops for current page
    offset = page * STOPS_PER_PAGE
    stops = await display_bus_stop_repo.get_all(limit=STOPS_PER_PAGE, offset=offset)

    if not stops:
        await callback.answer("❌ Нет остановок на этой странице", show_alert=True)
        return

    # Update message with new page
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        f"📋 <b>Выберите остановку:</b>\n\nСтраница {page + 1} из {total_pages}",
        reply_markup=build_stop_list_keyboard(
            stops, field, page=page, total_pages=total_pages
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    RouteMenuCallback.filter(F.action == RouteAction.BACK),
    StateFilter("*"),
)
async def handle_back_button(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: RouteMenuCallback,
):
    """
    Handle back button navigation.

    Returns user to the route menu from any state.
    """
    # Return to menu state
    await state.set_state(BusRouteStates.menu)

    # Get current route data
    data = await state.get_data()

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "🚌 <b>Планирование маршрута</b>\n\nВыберите параметры вашей поездки:",
        reply_markup=build_route_menu_keyboard(
            origin=data.get("origin_name"),
            destination=data.get("destination_name"),
            departure=data.get("departure_time"),
            arrival=data.get("arrival_time"),
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.in_(["disabled_back", "disabled_forward", "page_info"]))
async def handle_disabled_navigation(callback: CallbackQuery):
    """
    Handle clicks on disabled navigation buttons.

    Simply answers the callback without doing anything to prevent
    "query is too old" errors and provide feedback to user.
    """
    await callback.answer()  # Silent answer - no alert
