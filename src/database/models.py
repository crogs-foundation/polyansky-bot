from datetime import datetime, time
from typing import List

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pass


class DisplayBusStop(Base):
    __tablename__ = "display_bus_stops"
    name: Mapped[str] = mapped_column(String(63), index=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    search: Mapped[str] = mapped_column(String(1023))

    stops: Mapped[List["BusStop"]] = relationship(
        "BusStop", foreign_keys="[BusStop.name]", back_populates="display_name"
    )

    def __repr__(self) -> str:
        return f"<DisplayBusStop(name='{self.name}')>"


class BusStop(Base):
    """Bus stop model representing physical bus stations."""

    __tablename__ = "bus_stops"

    code: Mapped[str] = mapped_column(
        String(7), nullable=False, unique=True, index=True
    )  # 7-letter unique code
    name: Mapped[str] = mapped_column(
        String(63),
        ForeignKey("display_bus_stops.name", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    address: Mapped[str] = mapped_column(String(63), nullable=False)
    address_distance: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Field to distinguish stops on different sides of the road
    side_identifier: Mapped[str] = mapped_column(
        String(50), nullable=True
    )  # e.g., "A", "B", "North", "South"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    route_stops: Mapped[List["RouteStop"]] = relationship(
        "RouteStop",
        back_populates="bus_stop",
        cascade="all, delete-orphan",
        order_by="RouteStop.stop_order",
    )
    routes_as_origin: Mapped[List["BusRoute"]] = relationship(
        "BusRoute",
        foreign_keys="[BusRoute.origin_stop_code]",
        back_populates="origin_stop",
    )
    routes_as_destination: Mapped[List["BusRoute"]] = relationship(
        "BusRoute",
        foreign_keys="[BusRoute.destination_stop_code]",
        back_populates="destination_stop",
    )
    stop_schedules: Mapped[List["StopSchedule"]] = relationship(
        "StopSchedule", back_populates="stop", cascade="all, delete-orphan"
    )

    display_name: Mapped[DisplayBusStop] = relationship(
        "DisplayBusStop", back_populates="stops"
    )

    # Ensure unique combination of name, latitude, and longitude
    __table_args__ = (
        UniqueConstraint("code", "latitude", "longitude", name="uix_stop_location"),
    )

    def __repr__(self) -> str:
        side = f" ({self.side_identifier})" if self.side_identifier else ""
        return f"<BusStop(code='{self.code}', name='{self.name}{side}')>"


class BusRoute(Base):
    """Bus route model representing a specific bus line."""

    __tablename__ = "bus_routes"

    name: Mapped[str] = mapped_column(String(31), nullable=False, index=True, unique=True)
    origin_stop_code: Mapped[str] = mapped_column(
        String(7), ForeignKey("bus_stops.code", ondelete="CASCADE"), nullable=False
    )
    destination_stop_code: Mapped[str] = mapped_column(
        String(7), ForeignKey("bus_stops.code", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=True
    )  # Human-friendly description
    color: Mapped[str] = mapped_column(
        String(7), nullable=True
    )  # Hex color code for display (e.g., "#FF5733")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )  # Can disable routes without deleting
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    origin_stop: Mapped["BusStop"] = relationship(
        "BusStop", foreign_keys=[origin_stop_code], back_populates="routes_as_origin"
    )
    destination_stop: Mapped["BusStop"] = relationship(
        "BusStop",
        foreign_keys=[destination_stop_code],
        back_populates="routes_as_destination",
    )
    route_stops: Mapped[List["RouteStop"]] = relationship(
        "RouteStop", back_populates="route", cascade="all, delete-orphan"
    )
    schedules: Mapped[List["RouteSchedule"]] = relationship(
        "RouteSchedule", back_populates="route", cascade="all, delete-orphan"
    )
    stop_schedules: Mapped[List["StopSchedule"]] = relationship(
        "StopSchedule", back_populates="route", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BusRoute(id={self.id}, name='{self.name}', {self.origin_stop_code} -> {self.destination_stop_code})>"


class RouteStop(Base):
    """
    Route stop configuration - defines which stops are on a route and in what order.

    This is the association table that creates many-to-many relationship
    between routes and stops with ordering information.
    """

    __tablename__ = "route_stops"

    route_name: Mapped[str] = mapped_column(
        String(31), ForeignKey("bus_routes.name", ondelete="CASCADE"), nullable=False
    )
    stop_code: Mapped[str] = mapped_column(
        String(7), ForeignKey("bus_stops.code", ondelete="CASCADE"), nullable=False
    )
    stop_order: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Order in route sequence

    # Relationships
    route: Mapped["BusRoute"] = relationship("BusRoute", back_populates="route_stops")
    bus_stop: Mapped["BusStop"] = relationship("BusStop", back_populates="route_stops")

    __table_args__ = (
        UniqueConstraint("route_name", "stop_code", name="uix_route_stop_order"),
    )

    def __repr__(self) -> str:
        return (
            f"<RouteStop(route_name={self.route_name}, "
            f"stop_code={self.stop_code}, order={self.stop_order})>"
        )


class RouteSchedule(Base):
    """
    Route schedule - defines departure times for specific routes.

    Each entry represents a scheduled departure time for a route.
    The actual stops and their order are defined in RouteStop.
    """

    __tablename__ = "route_schedules"

    route_name: Mapped[str] = mapped_column(
        String(31), ForeignKey("bus_routes.name", ondelete="CASCADE"), nullable=False
    )
    departure_time: Mapped[time] = mapped_column(
        Time, nullable=False, index=True
    )  # Departure time from first stop
    valid_from: Mapped[time] = mapped_column(
        Time, nullable=True
    )  # Time when this schedule becomes valid (e.g., 06:00 for morning service)
    valid_until: Mapped[time] = mapped_column(
        Time, nullable=True
    )  # Time when this schedule expires (e.g., 22:00 for evening cutoff)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )  # Can be used to disable specific times

    monday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    tuesday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    wednesday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    thursday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    friday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    saturday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    sunday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )

    # Relationships
    route: Mapped["BusRoute"] = relationship("BusRoute", back_populates="schedules")

    # TODO fix constraint
    __table_args__ = (
        # UniqueConstraint(
        #     "route_name", "departure_time",
        #     "monday","tuesday","wednesday",
        #     "thursday","friday","saturday",
        #     "sunday", name="uix_route_departure"
        # ),
    )

    def __repr__(self) -> str:
        return (
            f"<RouteSchedule(route_name={self.route_name}, "
            f"departure={self.departure_time})>"
        )


class StopSchedule(Base):
    """
    Stop schedule - defines when a bus arrives at each specific stop along a route.

    This model links routes, stops, and arrival times to create a complete
    timetable for each stop on each route.
    """

    __tablename__ = "stop_schedules"

    trip_id: Mapped[str] = mapped_column(String(31), nullable=False, index=True)
    route_name: Mapped[str] = mapped_column(
        String(31), ForeignKey("bus_routes.name", ondelete="CASCADE"), nullable=False
    )
    stop_code: Mapped[str] = mapped_column(
        String(7), ForeignKey("bus_stops.code", ondelete="CASCADE"), nullable=False
    )
    arrival_time: Mapped[time] = mapped_column(
        Time, nullable=False, index=True
    )  # Arrival time at this specific stop
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    monday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    tuesday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    wednesday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    thursday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    friday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    saturday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )
    sunday: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=False
    )

    # Relationships
    route: Mapped["BusRoute"] = relationship("BusRoute", back_populates="stop_schedules")
    stop: Mapped["BusStop"] = relationship("BusStop", back_populates="stop_schedules")

    # TODO: Fix unique constraint
    __table_args__ = (
        # UniqueConstraint(
        #     "route_name", "stop_code", "arrival_time", name="uix_route_stop_arrival"
        # ),
    )

    def __repr__(self) -> str:
        return (
            f"<StopSchedule(route_name={self.route_name}, stop_code={self.stop_code}, "
            f"arrival={self.arrival_time})>"
        )


class RouteSearch(Base):
    __tablename__ = "route_search"

    telegram_user_id: Mapped[int] = mapped_column(Integer, index=True)
    origin: Mapped[str] = mapped_column(String(63), ForeignKey("display_bus_stops.name"))
    destination: Mapped[str] = mapped_column(
        String(63), ForeignKey("display_bus_stops.name")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<StopSchedule(origin={self.origin}, destination={self.destination}, "
            f"created_at={self.created_at})>"
        )
