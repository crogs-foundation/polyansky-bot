"""Finite State Machine states for route planning."""

from aiogram.fsm.state import State, StatesGroup


class BusRouteStates(StatesGroup):
    """States for multi-step route planning conversation."""

    # Main menu state
    menu = State()

    # Input states for origin selection
    waiting_origin_location = State()
    waiting_origin_list = State()
    waiting_origin_search = State()

    # Input states for destination selection
    waiting_destination_location = State()
    waiting_destination_list = State()
    waiting_destination_search = State()

    # Time input states
    waiting_departure_time = State()
    waiting_arrival_time = State()

    waiting_route_chose = State()
