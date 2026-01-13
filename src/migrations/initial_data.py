"""Load initial bus stops and routes data."""

import asyncio
import csv
from datetime import time
from pathlib import Path

from bot.config import load_config
from database.connection import DatabaseManager
from database.repositories.bus_route import BusRouteRepository
from database.repositories.bus_route_schedule import BusRouteScheduleRepository
from database.repositories.bus_route_stop import BusRouteStopRepository
from database.repositories.bus_stop import BusStopRepository
from database.repositories.bus_stop_schedule import BusStopScheduleRepository


async def load_bus_stops(csv_path: Path, db_manager: DatabaseManager) -> dict:
    """
    Load bus stops from CSV.

    Returns:
        dict: Mapping of code to stop object
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

        with open(csv_path, "r", encoding="utf-8") as f:
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
):
    """
    Load route stop configurations from CSV.
    """
    async with db_manager.session() as session:
        repo = BusRouteStopRepository(session)
        route_stop_count = 0

        with open(csv_path, "r", encoding="utf-8") as f:
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

        print(f"✓ Loaded {route_stop_count} route stop configurations from {csv_path}")


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

        with open(csv_path, "r", encoding="utf-8") as f:
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
):
    """
    Load stop schedules from CSV using bulk insert.
    """
    async with db_manager.session() as session:
        repo = BusStopScheduleRepository(session)
        schedule_data = []
        skipped_count = 0

        with open(csv_path, "r", encoding="utf-8") as f:
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

                schedule_data.append(
                    {
                        "route_name": route.name,
                        "stop_code": stop.code,
                        "arrival_time": arrival_time,
                        "is_active": row["is_active"].lower() == "true"
                        if "is_active" in row
                        else True,
                        "service_days": service_days,
                    }
                )

        if schedule_data:
            await repo.add_bulk(schedule_data)
            print(
                f"✓ Loaded {len(schedule_data)} stop schedules from {csv_path} (bulk insert)"
            )

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
        await load_route_stops(
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
