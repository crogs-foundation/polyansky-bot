"""Callback data models for inline keyboards."""

from enum import Enum

from aiogram.filters.callback_data import CallbackData


class RouteAction(str, Enum):
    """Actions available in route planning menu."""

    MAIN_MENU = "main_menu"
    START_BUSES = "start_buses"
    EDIT_ORIGIN = "origin"
    EDIT_DESTINATION = "destination"
    EDIT_DEPARTURE = "departure"
    EDIT_ARRIVAL = "arrival"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    BACK = "back"
    START_ORGANIZATIONS = "start_organizations"  # NEW


class InputMethod(str, Enum):
    """Methods for selecting bus stops."""

    LOCATION = "location"  # Send location on map
    LIST = "list"  # Choose from paginated list
    SEARCH = "search"  # Type to search


# NEW: Organization actions and callbacks
class OrganizationAction(str, Enum):
    """Actions for organization menu."""

    SHOW_CATEGORIES = "show_categories"
    SHOW_ORGANIZATIONS = "show_organizations"
    SELECT_CATEGORY = "select_category"
    SELECT_ORGANIZATION = "select_organization"
    BACK = "back"
    SEARCH = "search"
    NEXT_PAGE = "next_page"
    PREV_PAGE = "prev_page"


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


# NEW: Organization callbacks
class OrganizationMenuCallback(CallbackData, prefix="org_menu"):
    """Callback for organization main menu."""

    action: OrganizationAction
    page: int = 0
    category_id: int | None = None


class CategoryListCallback(CallbackData, prefix="category"):
    """Callback for category selection."""

    category_id: int
    page: int = 0


class OrganizationListCallback(CallbackData, prefix="organization"):
    """Callback for organization selection."""

    organization_id: int
    page: int = 0
    category_id: int | None = None


class AdminAction(str, Enum):
    """Actions for admin menu."""

    ADD_CATEGORY = "add_category"
    ADD_ORGANIZATION = "add_organization"
    CONFIRM_CATEGORY = "confirm_category"
    CONFIRM_ORGANIZATION = "confirm_organization"
    CANCEL = "cancel"


# Добавить новый callback:
class AdminCallback(CallbackData, prefix="admin"):
    """Callback data for admin actions."""

    action: AdminAction
