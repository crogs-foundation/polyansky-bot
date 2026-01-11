"""Load initial bus stops and routes data."""

import asyncio
import csv
from datetime import time
from pathlib import Path

from bot.config import load_config
from database.connection import DatabaseManager
from database.repositories.bus_route import BusRouteRepository
from database.repositories.bus_route_stop import BusRouteStopRepository
from database.repositories.bus_schedule import BusRouteScheduleRepository
from database.repositories.bus_stop import BusStopRepository


async def load_bus_stops(csv_path: Path, db_manager: DatabaseManager) -> dict:
    """
    Load bus stops from CSV.

    Returns:
        dict: Mapping of code to stop_id for later use
    """
    async with db_manager.session() as session:
        repo = BusStopRepository(session)
        stop_mapping = {}

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                side_id = (
                    row["side_identifier"].strip()
                    if row["side_identifier"].strip()
                    else None
                )

                stop = await repo.create(
                    code=row["code"],
                    name=row["name"],
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    is_active=row["is_active"].lower() == "true",
                    side_identifier=side_id,
                )

                # Create mapping: code -> stop_id
                stop_mapping[row["code"]] = stop.id

        print(f"✓ Loaded {len(stop_mapping)} bus stops from {csv_path}")
        return stop_mapping


async def load_bus_routes(csv_path: Path, db_manager: DatabaseManager) -> dict:
    """
    Load bus routes from CSV.

    Returns:
        dict: Mapping of (route_number, origin_code, destination_code) to route_id for later use
    """
    async with db_manager.session() as session:
        repo = BusRouteRepository(session)
        route_mapping = {}

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route = await repo.create(
                    route_number=row["route_number"],
                    origin_stop_code=row["origin_stop_code"],
                    destination_stop_code=row["destination_stop_code"],
                    description=row["description"]
                    if row["description"].strip()
                    else None,
                    color=row["color"] if row["color"].strip() else None,
                    is_active=row["is_active"].lower() == "true",
                )
                # Create mapping key: (route_number, origin_code, destination_code)
                key = (
                    row["route_number"],
                    row["origin_stop_code"],
                    row["destination_stop_code"],
                )
                route_mapping[key] = route.id

        print(f"✓ Loaded {len(route_mapping)} bus routes from {csv_path}")
        return route_mapping


async def load_route_stops(
    csv_path: Path,
    db_manager: DatabaseManager,
    stop_mapping: dict,
    route_mapping: dict,
):
    """
    Load route stop configurations from CSV.

    This defines which stops belong to which routes and in what order.

    Args:
        csv_path: Path to the route_stops CSV file
        db_manager: Database manager instance
        stop_mapping: Mapping of stop_code to stop_id
        route_mapping: Mapping of (route_number, origin_code, destination_code) to route_id
    """
    async with db_manager.session() as session:
        repo = BusRouteStopRepository(session)
        route_stop_count = 0

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Get route_id using route_number, origin, and destination
                route_key = (
                    row["route_number"],
                    row["origin_stop_code"],
                    row["destination_stop_code"],
                )
                route_id = route_mapping.get(route_key)
                if not route_id:
                    print(
                        f"Warning: Route {row['route_number']} ({row['origin_stop_code']} -> {row['destination_stop_code']}) not found, skipping route stop entry"
                    )
                    continue

                # Get stop_id
                stop_id = stop_mapping.get(row["stop_code"])

                if not stop_id:
                    print(f"Warning: Stop '{row['stop_code']}' not found, skipping")
                    continue

                # Create route stop entry
                await repo.create(
                    route_id=route_id,
                    bus_stop_id=stop_id,
                    stop_order=int(row["stop_order"]),
                )
                route_stop_count += 1

        print(f"✓ Loaded {route_stop_count} route stop configurations from {csv_path}")


async def load_route_schedules(
    csv_path: Path,
    db_manager: DatabaseManager,
    route_mapping: dict,
):
    """
    Load route schedules from CSV.

    This defines departure times for each route.

    Args:
        csv_path: Path to the schedules CSV file
        db_manager: Database manager instance
        route_mapping: Mapping of (route_number, origin_code, destination_code) to route_id
    """
    async with db_manager.session() as session:
        repo = BusRouteScheduleRepository(session)
        schedule_count = 0

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Get route_id using route_number, origin, and destination
                route_key = (
                    row["route_number"],
                    row["origin_stop_code"],
                    row["destination_stop_code"],
                )
                route_id = route_mapping.get(route_key)
                if not route_id:
                    print(
                        f"Warning: Route {row['route_number']} ({row['origin_stop_code']} -> {row['destination_stop_code']}) not found, skipping schedule entry"
                    )
                    continue

                # Parse departure time
                time_parts = row["departure_time"].strip().split(":")
                departure_time = time(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=int(time_parts[2]) if len(time_parts) > 2 else 0,
                )

                # Parse service_days
                service_days = int(row["service_days"])

                # Parse valid_from and valid_until times
                valid_from = None
                if row["valid_from"].strip():
                    time_parts = row["valid_from"].strip().split(":")
                    valid_from = time(
                        hour=int(time_parts[0]),
                        minute=int(time_parts[1]),
                        second=int(time_parts[2]) if len(time_parts) > 2 else 0,
                    )

                valid_until = None
                if row["valid_until"].strip():
                    time_parts = row["valid_until"].strip().split(":")
                    valid_until = time(
                        hour=int(time_parts[0]),
                        minute=int(time_parts[1]),
                        second=int(time_parts[2]) if len(time_parts) > 2 else 0,
                    )

                # Create schedule entry
                await repo.create(
                    route_id=route_id,
                    departure_time=departure_time,
                    service_days=service_days,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    is_active=row["is_active"].lower() == "true",
                )
                schedule_count += 1

        print(f"✓ Loaded {schedule_count} route schedules from {csv_path}")


async def main():
    """Main function to load all initial data."""
    config = load_config()
    db_manager = DatabaseManager(config.database.path)
    await db_manager.init_database()

    print("=" * 60)
    print("Loading initial data...")
    print("=" * 60)

    try:
        # Load data in order (stops -> routes -> route_stops -> schedules)
        data_dir = Path("data")

        print("\n1. Loading bus stops...")
        stop_mapping = await load_bus_stops(data_dir / "stops.csv", db_manager)

        print("\n2. Loading bus routes...")
        route_mapping = await load_bus_routes(data_dir / "routes.csv", db_manager)

        print("\n3. Loading route stop configurations...")
        await load_route_stops(
            data_dir / "route_stops.csv",
            db_manager,
            stop_mapping,
            route_mapping,
        )

        print("\n4. Loading route schedules...")
        await load_route_schedules(
            data_dir / "route_schedules.csv",
            db_manager,
            route_mapping,
        )

        print("\n" + "=" * 60)
        print("✓ All data loaded successfully!")
        print("=" * 60)

    except FileNotFoundError as e:
        print(f"\n✗ Error: CSV file not found - {e}")
        print("Please ensure all CSV files are in the 'data' directory:")
        print("  - data/bus_stops.csv")
        print("  - data/bus_routes.csv")
        print("  - data/route_stops.csv")
        print("  - data/route_schedules.csv")
    except Exception as e:
        print(f"\n✗ Error loading data: {e}")
        raise
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
