"""Load initial bus stops and routes data."""

import asyncio
import csv
from pathlib import Path

from bot.config import load_config
from database.connection import DatabaseManager
from database.repositories.bus_stop import BusStopRepository


async def load_bus_stops(csv_path: Path, db_manager: DatabaseManager):
    """Load bus stops from CSV."""
    async with db_manager.session() as session:
        repo = BusStopRepository(session)

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                await repo.create(
                    name=row["name"],
                    address=row["address"],
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                )
        print(f"Loaded bus stops from {csv_path}")


async def main():
    config = load_config()
    db_manager = DatabaseManager(config.database.path)
    await db_manager.init_database()

    # Load data
    await load_bus_stops(Path("data/bus_stops.csv"), db_manager)

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
