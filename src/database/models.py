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

    pass


class BusStop(Base):
    """Bus stop model representing physical bus stations."""

    __tablename__ = "bus_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    schedules: Mapped[List["RouteSchedule"]] = relationship(
        "RouteSchedule", back_populates="bus_stop", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BusStop(id={self.id}, name='{self.name}')>"


class BusRoute(Base):
    """Bus route model representing a specific bus line."""

    __tablename__ = "bus_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "A -> B"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    schedules: Mapped[List["RouteSchedule"]] = relationship(
        "RouteSchedule", back_populates="route", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("route_number", "direction", name="uix_route_direction"),
    )

    def __repr__(self) -> str:
        return f"<BusRoute(id={self.id}, number='{self.route_number}', direction='{self.direction}')>"


class RouteSchedule(Base):
    """
    Schedule entry linking routes to stops with timing information.

    This is the association table that creates many-to-many relationship
    between routes and stops with additional scheduling data.
    """

    __tablename__ = "route_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bus_routes.id", ondelete="CASCADE"), nullable=False
    )
    bus_stop_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bus_stops.id", ondelete="CASCADE"), nullable=False
    )
    stop_order: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Order in route sequence
    departure_time: Mapped[time] = mapped_column(
        Time, nullable=True
    )  # Null for intermediate stops
    is_key_stop: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # True if has scheduled departure

    # Relationships
    route: Mapped["BusRoute"] = relationship("BusRoute", back_populates="schedules")
    bus_stop: Mapped["BusStop"] = relationship("BusStop", back_populates="schedules")

    __table_args__ = (
        UniqueConstraint(
            "route_id", "bus_stop_id", "stop_order", name="uix_route_stop_order"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RouteSchedule(route_id={self.route_id}, "
            f"stop_id={self.bus_stop_id}, order={self.stop_order})>"
        )
