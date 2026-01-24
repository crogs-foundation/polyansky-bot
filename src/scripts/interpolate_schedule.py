import csv
import os
from collections import defaultdict

from loguru import logger

from utils.get_path import create_path


def load_csv(filename, directory="./data"):
    """Load CSV file and return list of dictionaries"""
    filepath = os.path.join(directory, filename)
    data = []

    try:
        with open(create_path(filepath), "r", encoding="utf-8") as file:
            # Read first line to get headers
            first_line = file.readline().strip()
            fieldnames = [field.strip() for field in first_line.split(",")]

            reader = csv.DictReader(file, fieldnames=fieldnames)

            data = list(reader)

        logger.info(f"Loaded {len(data)} records from {filename}")
        return data
    except FileNotFoundError:
        logger.error(f"File {filepath} not found")
        raise
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        raise


def load_partial_schedule(filename, directory="./data") -> list[list[dict]]:
    """Load partial schedule CSV with blank lines separating trips"""
    filepath = os.path.join(directory, filename)
    trips = []  # List of trips, each trip is a list of stops
    try:
        with open(create_path(filepath), "r", encoding="utf-8") as f:
            fieldnames = f.readline().strip().split(",")
            content = f.read()

        # Process each block (separated by empty lines)
        blocks = content.strip().split("\n\n")

        for block in blocks:
            if not block.strip():
                continue

            lines = block.strip().split("\n")
            reader = csv.DictReader(lines, fieldnames=fieldnames)
            trip_stops = []

            for row in reader:
                trip_stops.append(
                    {
                        "route_name": row["route_name"],
                        "stop_code": row["stop_code"],
                        "arrival_time": row["arrival_time"],
                        "is_active": row["is_active"] == "True",
                        "service_days": row["service_days"],
                    }
                )

            if trip_stops:
                trips.append(trip_stops)

        logger.info(f"Loaded {sum(len(trips) for trips in trips)} trips from {filepath}")

    except FileNotFoundError:
        logger.error(f"Partial schedule file not found: {filepath}")
        return trips
    except Exception as e:
        logger.error(f"Error loading partial schedule: {e}")
        return trips
    return trips


def save_csv(data, filename, fieldnames, directory="./data"):
    """Save data to CSV file"""
    filepath = os.path.join(directory, filename)

    try:
        with open(create_path(filepath), "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"Saved {len(data)} records to {filename}")
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")
        raise


def time_to_seconds(time_str):
    """Convert HH:MM:SS string to seconds"""
    try:
        # Handle both HH:MM:SS and H:MM:SS formats
        parts = time_str.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            hours, minutes = map(int, parts)
            return hours * 3600 + minutes * 60
        else:
            raise ValueError(f"Invalid time format: {time_str}")
    except Exception as e:
        logger.error(f"Error converting time {time_str}: {e}")
        raise


def seconds_to_time(seconds):
    """Convert seconds to HH:MM:SS string"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def interpolate_stop_times(route_stops, trips, routes_info):
    """
    Interpolate arrival times for intermediate stops

    Args:
        route_stops: List of all stops in route order
        trips: List of trips, each trip is a list of stops with known times
        routes_info: Dictionary with route information

    Returns:
        List of interpolated schedule entries
    """
    interpolated_schedule = []

    # Create a dictionary mapping route names to their stops in order
    route_stops_map = defaultdict(list)
    for stop in route_stops:
        route_stops_map[stop["route_name"]].append(stop)

    # Sort stops by stop_order for each route
    for route_name in route_stops_map:
        route_stops_map[route_name].sort(key=lambda x: int(x["stop_order"]))

    # Process each trip
    for trip_idx, trip in enumerate(trips):
        if not trip:
            continue

        # Get route name from first stop in trip
        route_name = trip[0]["route_name"]
        logger.debug(f"Processing trip {trip_idx + 1} for route {route_name}")

        # Get all stops for this route in order
        route_stops_list = route_stops_map.get(route_name)
        if not route_stops_list:
            logger.warning(f"No route stops found for route: {route_name}")
            continue

        # Create mapping of stop_code to index
        stop_index_map = {
            stop["stop_code"]: idx for idx, stop in enumerate(route_stops_list)
        }

        # Get trip metadata from first stop
        first_stop = trip[0]
        is_active = first_stop["is_active"]
        service_days = first_stop["service_days"]

        # Create list of known stops with their indices and times
        known_stops = []
        for stop_data in trip:
            stop_code = stop_data["stop_code"]
            if stop_code in stop_index_map:
                idx = stop_index_map[stop_code]
                seconds = time_to_seconds(stop_data["arrival_time"])
                known_stops.append(
                    {
                        "index": idx,
                        "stop_code": stop_code,
                        "seconds": seconds,
                        "original_data": stop_data,
                    }
                )
            else:
                logger.warning(
                    f"Stop {stop_code} not found in route stops for {route_name}"
                )

        # Sort known stops by index
        known_stops.sort(key=lambda x: x["index"])

        if len(known_stops) < 2:
            logger.warning(
                f"Trip {trip_idx + 1} for route {route_name} has less than 2 known stops, skipping"
            )
            continue

        # Process the entire trip from first known stop to last known stop
        first_idx = known_stops[0]["index"]
        last_idx = known_stops[-1]["index"]

        # Create a dictionary of known times for quick lookup
        known_times_dict = {stop["index"]: stop["seconds"] for stop in known_stops}

        # For each stop in the route between first and last known stops
        for current_idx in range(first_idx, last_idx + 1):
            current_stop = route_stops_list[current_idx]

            if current_idx in known_times_dict:
                # This is a known stop - use the exact time
                current_time = known_times_dict[current_idx]
            else:
                # This is an unknown stop - need to interpolate
                # Find the surrounding known stops
                left_idx = None
                right_idx = None

                # Find the closest known stop to the left
                for i in range(len(known_stops) - 1, -1, -1):
                    if known_stops[i]["index"] < current_idx:
                        left_idx = known_stops[i]
                        break

                # Find the closest known stop to the right
                for i in range(len(known_stops)):
                    if known_stops[i]["index"] > current_idx:
                        right_idx = known_stops[i]
                        break

                if left_idx is None or right_idx is None:
                    # Can't interpolate - skip this stop
                    logger.warning(
                        f"Cannot interpolate stop {current_stop['stop_code']} at index {current_idx}"
                    )
                    continue

                # Linear interpolation
                left_index = left_idx["index"]
                right_index = right_idx["index"]
                left_time = left_idx["seconds"]
                right_time = right_idx["seconds"]

                # Calculate interpolated time
                time_per_segment = (right_time - left_time) / (right_index - left_index)
                current_time = left_time + (current_idx - left_index) * time_per_segment

            # Add to interpolated schedule
            interpolated_schedule.append(
                {
                    "route_name": route_name,
                    "stop_code": current_stop["stop_code"],
                    "arrival_time": seconds_to_time(round(current_time)),
                    "is_active": is_active,
                    "service_days": service_days,
                }
            )

    return interpolated_schedule


def generate_route_schedules(trips: list[list[dict]]) -> list[dict]:
    route_schedule = []
    for trip in trips:
        first_stop = trip[0]
        route_schedule.append(
            {
                "route_name": first_stop["route_name"],
                "departure_time": first_stop["arrival_time"],
                "service_days": first_stop["service_days"],
                "is_active": first_stop["is_active"],
            }
        )

    return route_schedule


def main():
    """Main function to load data, interpolate stops, and save results"""
    logger.info("Starting schedule interpolation...")

    try:
        # Load data
        trips = load_partial_schedule("partial_stops_schedule.csv")
        routes = load_csv("routes.csv")
        route_stops = load_csv("route_stops.csv")

        logger.info(f"Loaded {len(trips)} trips")
        logger.info(f"Loaded {len(routes)} routes")
        logger.info(f"Loaded {len(route_stops)} route stops")

        # Create routes info dictionary for quick lookup
        routes_info = {route["name"]: route for route in routes}

        # Count total stops in partial schedule
        total_partial_stops = sum(len(trip) for trip in trips)
        logger.info(f"Total stops in partial schedule: {total_partial_stops}")

        # Interpolate stop times
        interpolated_data = interpolate_stop_times(route_stops, trips, routes_info)

        logger.info(f"Generated {len(interpolated_data)} interpolated schedule entries")

        # Save interpolated schedule
        fieldnames = [
            "route_name",
            "stop_code",
            "arrival_time",
            "is_active",
            "service_days",
        ]
        save_csv(interpolated_data, "interpolated_schedule.csv", fieldnames)

        route_schedule = generate_route_schedules(trips)
        logger.info(f"Loaded {len(route_schedule)} route schedules")

        fieldnames = ["route_name", "departure_time", "service_days", "is_active"]
        save_csv(route_schedule, "generated_route_schedules.csv", fieldnames)

        logger.success("Schedule interpolation completed successfully!")

        # Print summary
        print("\n=== Interpolation Summary ===")
        print(f"Total trips processed: {len(trips)}")
        print(f"Total partial schedule stops: {total_partial_stops}")
        print(f"Total interpolated entries: {len(interpolated_data)}")

        # Count by route
        route_counts = defaultdict(int)
        for entry in interpolated_data:
            route_counts[entry["route_name"]] += 1

        print("\nEntries per route:")
        for route, count in sorted(route_counts.items()):
            print(f"  {route}: {count} entries")

        print("\nOutput saved to: ./data/interpolated_schedule.csv")

    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise


if __name__ == "__main__":
    # Configure loguru
    logger.add("schedule_interpolation.log", level="INFO", rotation="10 MB")

    main()
