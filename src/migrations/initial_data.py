"""Load initial bus stops and routes data."""

import asyncio
import csv
from collections import defaultdict
from datetime import time
from pathlib import Path

from bot.config import load_config
from database.connection import DatabaseManager
from database.models import BusStop
from database.repositories.bus_route import BusRouteRepository
from database.repositories.bus_route_schedule import BusRouteScheduleRepository
from database.repositories.bus_route_stop import BusRouteStopRepository
from database.repositories.bus_stop import BusStopRepository
from database.repositories.bus_stop_schedule import BusStopScheduleRepository
from database.repositories.display_bus_stop import DisplayBusStopRepository
from utils.get_path import create_path


async def load_bus_stops(
    csv_path: Path, db_manager: DatabaseManager
) -> dict[str, BusStop]:
    """
    Load bus stops from CSV.

    Returns:
        dict: Mapping of code to stop object
    """
    async with db_manager.session() as session:
        repo = BusStopRepository(session)
        display_repo = DisplayBusStopRepository(session)

        names = set()
        stop_mapping = {}

        with open(create_path(csv_path), "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                side_id = (
                    row["side_identifier"].strip()
                    if row["side_identifier"].strip()
                    else None
                )

                name = row["name"]
                if name not in names:
                    await display_repo.create(name=name, search=name)
                    names.add(name)

                stop = await repo.create(
                    code=row["code"],
                    name=row["name"],
                    address=row["address"],
                    address_distance=float(row["address_dist"]),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    is_active=row["is_active"].lower() == "true",
                    side_identifier=side_id,
                )

                stop_mapping[row["code"]] = stop

        print(f"✓ Loaded {len(stop_mapping)} bus stops from {csv_path}")
        return stop_mapping


async def load_bus_routes(csv_path: Path, db_manager: DatabaseManager) -> dict:
    """
    Load bus routes from CSV.

    Returns:
        dict: Mapping of (name, origin_code, destination_code) to route object
    """
    async with db_manager.session() as session:
        repo = BusRouteRepository(session)
        route_mapping = {}

        with open(create_path(csv_path), "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route = await repo.create(
                    name=row["name"],
                    origin_stop_code=row["origin_stop_code"],
                    destination_stop_code=row["destination_stop_code"],
                    description=row["description"]
                    if row["description"].strip()
                    else None,
                    color=row["color"] if row["color"].strip() else None,
                    is_active=row["is_active"].lower() == "true",
                )

                route_mapping[row["name"]] = route

        print(f"✓ Loaded {len(route_mapping)} bus routes from {csv_path}")
        return route_mapping


async def load_route_stops(
    csv_path: Path,
    db_manager: DatabaseManager,
    stop_mapping: dict,
    route_mapping: dict,
) -> dict[str, int]:
    """
    Load route stop configurations from CSV.

    Returns:
        dict: Mapping of route_name to number of stops on that route
    """
    async with db_manager.session() as session:
        repo = BusRouteStopRepository(session)
        route_stop_count = 0
        stops_per_route = defaultdict(int)

        with open(create_path(csv_path), "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route = route_mapping.get(row["route_name"])
                if not route:
                    print(f"Warning: Route {row['route_name']} not found")
                    continue

                stop = stop_mapping.get(row["stop_code"])
                if not stop:
                    print(f"Warning: Stop '{row['stop_code']}' not found")
                    continue

                await repo.add(
                    route_name=route.name,
                    stop_code=stop.code,
                    stop_order=int(row["stop_order"]),
                )
                route_stop_count += 1
                stops_per_route[route.name] += 1

        print(f"✓ Loaded {route_stop_count} route stop configurations from {csv_path}")
        return dict(stops_per_route)


async def load_route_schedules(
    csv_path: Path,
    db_manager: DatabaseManager,
    route_mapping: dict,
):
    """
    Load route schedules from CSV.
    """
    async with db_manager.session() as session:
        repo = BusRouteScheduleRepository(session)
        schedule_count = 0

        with open(create_path(csv_path), "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route = route_mapping.get(row["route_name"])
                if not route:
                    print(f"Warning: Route {row['route_name']} not found")
                    continue

                # Parse time
                time_parts = row["departure_time"].strip().split(":")
                departure_time = time(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=int(time_parts[2]) if len(time_parts) > 2 else 0,
                )

                service_days = (
                    int(row["service_days"]) if row.get("service_days") else 127
                )
                await repo.add(
                    route_name=route.name,
                    departure_time=departure_time,
                    service_days=service_days,
                    is_active=row["is_active"].lower() == "true"
                    if "is_active" in row
                    else True,
                )
                schedule_count += 1

        print(f"✓ Loaded {schedule_count} route schedules from {csv_path}")


async def load_stop_schedules(
    csv_path: Path,
    db_manager: DatabaseManager,
    stop_mapping: dict,
    route_mapping: dict,
    stops_per_route: dict[str, int],
):
    """
    Load stop schedules from CSV using bulk insert with trip_id generation.

    Trip ID Generation Logic:
    - Schedules are grouped by route and service days
    - Within each group, schedules are ordered by arrival time
    - Every N schedules (where N = number of stops on the route) form one trip
    - Each trip gets a unique ID: route_name_trip_XXX

    Args:
        csv_path: Path to stop_schedules.csv
        db_manager: Database manager instance
        stop_mapping: Mapping of stop codes to stop objects
        route_mapping: Mapping of route names to route objects
        stops_per_route: Number of stops per route (from load_route_stops)
    """
    async with db_manager.session() as session:
        repo = BusStopScheduleRepository(session)
        skipped_count = 0

        # Group schedules by route and service days for trip assignment
        schedules_by_route_and_days = defaultdict(list)

        with open(create_path(csv_path), "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route = route_mapping.get(row["route_name"])
                if not route:
                    print(f"Warning: Route {row['route_name']} not found")
                    skipped_count += 1
                    continue

                stop = stop_mapping.get(row["stop_code"])
                if not stop:
                    print(f"Warning: Stop '{row['stop_code']}' not found")
                    skipped_count += 1
                    continue

                # Parse time
                time_parts = row["arrival_time"].strip().split(":")
                try:
                    arrival_time = time(
                        hour=int(time_parts[0]),
                        minute=int(time_parts[1]),
                        second=int(time_parts[2]) if len(time_parts) > 2 else 0,
                    )
                except (ValueError, IndexError):
                    print(
                        f"Warning: Invalid time format '{row['arrival_time']}', skipping"
                    )
                    skipped_count += 1
                    continue

                service_days = (
                    int(row["service_days"]) if row.get("service_days") else 127
                )
                is_active = (
                    row["is_active"].lower() == "true" if "is_active" in row else True
                )

                # Group by route and service days for trip ID assignment
                group_key = (route.name, service_days)
                schedules_by_route_and_days[group_key].append(
                    {
                        "route_name": route.name,
                        "stop_code": stop.code,
                        "arrival_time": arrival_time,
                        "is_active": is_active,
                        "service_days": service_days,
                    }
                )

        # Generate trip IDs for each group
        schedule_data = []
        for (route_name, service_days), schedules in schedules_by_route_and_days.items():
            # Sort by arrival time to ensure proper trip grouping
            schedules.sort(key=lambda x: x["arrival_time"])

            # Get number of stops for this route
            num_stops = stops_per_route.get(route_name, 1)

            # Assign trip IDs
            # Every num_stops schedules belong to the same trip
            for idx, schedule in enumerate(schedules):
                trip_number = (idx // num_stops) + 1
                trip_id = f"{route_name}_trip_{trip_number:03d}"
                schedule["trip_id"] = trip_id
                schedule_data.append(schedule)

        if schedule_data:
            await repo.add_bulk(schedule_data)
            print(
                f"✓ Loaded {len(schedule_data)} stop schedules from {csv_path} (bulk insert)"
            )

            # Print trip statistics
            trips_per_route = defaultdict(set)
            for schedule in schedule_data:
                trips_per_route[schedule["route_name"]].add(schedule["trip_id"])

            print("  Trip statistics:")
            for route_name in sorted(trips_per_route.keys()):
                num_trips = len(trips_per_route[route_name])
                print(f"    - {route_name}: {num_trips} trips")

        if skipped_count > 0:
            print(f"  Note: Skipped {skipped_count} invalid entries")


async def main():
    """Main function to load all initial data."""
    config = load_config()
    db_manager = DatabaseManager(config.database.path)
    await db_manager.init_database()

    print("=" * 60)
    print("Loading initial data...")
    print("=" * 60)

    try:
        data_dir = Path("data")

        print("\n1. Loading bus stops...")
        stop_mapping = await load_bus_stops(data_dir / "stops.csv", db_manager)

        print("\n2. Loading bus routes...")
        route_mapping = await load_bus_routes(data_dir / "routes.csv", db_manager)

        print("\n3. Loading route stop configurations...")
        stops_per_route = await load_route_stops(
            data_dir / "route_stops.csv",
            db_manager,
            stop_mapping,
            route_mapping,
        )

        print("\n4. Loading route schedules...")
        route_schedules_path = data_dir / "route_schedules.csv"
        if route_schedules_path.exists():
            await load_route_schedules(route_schedules_path, db_manager, route_mapping)
        else:
            print(f"  Note: {route_schedules_path} not found, skipping route schedules")

        print("\n5. Loading stop schedules...")
        stop_schedules_path = data_dir / "stop_schedules.csv"
        if stop_schedules_path.exists():
            await load_stop_schedules(
                stop_schedules_path,
                db_manager,
                stop_mapping,
                route_mapping,
                stops_per_route,
            )
        else:
            print(f"  Note: {stop_schedules_path} not found, skipping stop schedules")

        print("\n" + "=" * 60)
        print("✓ All data loaded successfully!")
        print("=" * 60)

    except FileNotFoundError as e:
        print(f"\n✗ Error: CSV file not found - {e}")
        print("Please ensure all CSV files are in the 'data' directory:")
        print("  - data/stops.csv")
        print("  - data/routes.csv")
        print("  - data/route_stops.csv")
        print("  - data/route_schedules.csv (optional)")
        print("  - data/stop_schedules.csv (optional)")
    except Exception as e:
        print(f"\n✗ Error loading data: {e}")
        raise
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
