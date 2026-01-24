"""Callback data models for inline keyboards."""

from enum import Enum

from aiogram.filters.callback_data import CallbackData


class RouteAction(str, Enum):
    """Actions available in route planning menu."""

    START_BUSES = "start_buses"
    EDIT_ORIGIN = "origin"
    EDIT_DESTINATION = "destination"
    EDIT_DEPARTURE = "departure"
    EDIT_ARRIVAL = "arrival"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    BACK = "back"  # NEW: For back navigation


class InputMethod(str, Enum):
    """Methods for selecting bus stops."""

    LOCATION = "location"  # Send location on map
    LIST = "list"  # Choose from paginated list
    SEARCH = "search"  # Type to search


class RouteMenuCallback(CallbackData, prefix="route"):
    """Callback data for route planning menu actions."""

    action: RouteAction


class InputMethodCallback(CallbackData, prefix="input"):
    """Callback data for input method selection."""

    field: str  # 'origin' or 'destination'
    method: InputMethod


class StopListCallback(CallbackData, prefix="stop"):
    """Callback data for bus stop selection from list."""

    stop_name: str
    field: str  # 'origin' or 'destination'


class ListNavigationCallback(CallbackData, prefix="nav"):
    """Callback data for list pagination."""

    page: int
    field: str


class TimePresetCallback(CallbackData, prefix="time"):
    """Callback data for preset time options."""

    field: str  # 'departure' or 'arrival'
    preset: str  # 'now' or 'asap'


class RouteChooseCallback(CallbackData, prefix="rc"):
    """Callback data for bus route selection from list."""

    index: int
    route_name: str
    origin_stop: str
    destination_stop: str
    departure_time: str  # HH:MM
    arrival_time: str  # HH:MM
    travel_duration: int  # minutes
