import csv
import random
from datetime import datetime, time, timedelta

from utils.get_path import create_path


def read_csv_file(filename):
    """Read CSV file and return list of dictionaries."""
    with open(create_path(filename), "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv_file(filename, data, fieldnames):
    """Write data to CSV file."""
    with open(create_path(filename), "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


def generate_route_schedules(routes):
    """Generate realistic route schedules for each route."""
    route_schedules = []

    # Define frequency patterns for different routes
    # Pattern: (start_time, end_time, interval_minutes, peak_interval_minutes)
    patterns = {
        # High frequency routes (every 15-30 min)
        "1": (time(6, 0), time(22, 30), 30, 15),
        "2": (time(6, 10), time(22, 40), 30, 15),
        # Medium frequency routes (every 30-60 min)
        "4": (time(6, 25), time(22, 25), 60, 30),
        # Lower frequency routes (every 60-120 min)
        "3": (time(6, 20), time(22, 20), 120, 90),
        "5": (time(6, 40), time(22, 40), 90, 60),
        "6": (time(6, 5), time(22, 5), 90, 60),
    }

    for route in routes:
        route_name = route["route_name"]
        if route_name not in patterns:
            continue

        start_time, end_time, interval, peak_interval = patterns[route_name]

        # Generate departure times
        current_time = datetime.combine(datetime.today(), start_time)
        end_datetime = datetime.combine(datetime.today(), end_time)

        while current_time <= end_datetime:
            hour = current_time.hour

            # Different intervals for peak vs off-peak hours
            if 7 <= hour <= 9 or 16 <= hour <= 18:  # Peak hours
                current_interval = peak_interval
            else:
                current_interval = interval

            # Add some randomness (±2 minutes)
            random_offset = random.randint(-2, 2)
            departure_time = (current_time + timedelta(minutes=random_offset)).time()

            # Determine service days
            # 127 = All days, 31 = Weekdays (Mon-Fri), 96 = Weekend (Sat-Sun)
            if route_name in ["1", "2"]:  # Main routes run every day
                service_days = 127
            elif route_name == "6":  # Some routes might not run on Sunday
                service_days = 126  # All days except Sunday
            else:
                service_days = 127

            # Add valid_from/valid_until for some routes (optional)
            valid_from = None
            valid_until = None

            # Routes to train station might have limited hours
            if route_name == 6:
                valid_from = time(5, 30)
                valid_until = time(23, 0)

            route_schedules.append(
                {
                    "route_name": route_name,
                    "departure_time": departure_time.strftime("%H:%M:%S"),
                    "service_days": service_days,
                    "valid_from": valid_from.strftime("%H:%M:%S") if valid_from else "",
                    "valid_until": valid_until.strftime("%H:%M:%S")
                    if valid_until
                    else "",
                    "is_active": "True",
                }
            )

            current_time += timedelta(minutes=current_interval)

    return route_schedules


def generate_stop_schedules(routes, route_stops, route_schedules):
    """Generate stop schedules based on route schedules and stop sequences."""
    stop_schedules = []

    # Group route stops by route
    route_stops_by_route = {}
    for rs in route_stops:
        route_num = rs["route_name"]
        if route_num not in route_stops_by_route:
            route_stops_by_route[route_num] = []
        route_stops_by_route[route_num].append(rs)

    # For each route, sort stops by order
    for route_num in route_stops_by_route:
        route_stops_by_route[route_num].sort(key=lambda x: int(x["stop_order"]))

    # Process each route schedule
    for schedule in route_schedules:
        route_num = schedule["route_name"]

        if route_num not in route_stops_by_route:
            continue

        stops = route_stops_by_route[route_num]
        departure_time = datetime.strptime(schedule["departure_time"], "%H:%M:%S")

        # Calculate travel times between stops
        # Base time plus variation based on route characteristics
        base_time_per_stop = 4  # minutes
        variation = random.uniform(0.8, 1.2)  # ±20% variation

        current_time = departure_time

        for i, stop in enumerate(stops):
            # First stop has departure time as arrival time
            if i == 0:
                arrival_time = current_time
            else:
                # Add travel time with some variation
                travel_minutes = base_time_per_stop * variation

                # Longer travel for certain conditions
                if "PEREEZD" in stop["stop_code"] or "VOKZAL" in stop["stop_code"]:
                    travel_minutes += 2  # Extra time for transfer points

                # Add random delay (0-3 minutes)
                delay = random.randint(0, 3)
                travel_minutes += delay

                current_time += timedelta(minutes=travel_minutes)
                arrival_time = current_time

            # Some stops might be skipped occasionally (5% chance)
            if random.random() > 0.95:
                continue

            stop_schedules.append(
                {
                    "route_name": route_num,
                    "stop_code": stop["stop_code"],
                    "arrival_time": arrival_time.strftime("%H:%M:%S"),
                    "is_active": "True",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

    return stop_schedules


def main():
    print("Reading data files...")

    # Read existing data
    routes = read_csv_file("./data/routes.csv")
    route_stops = read_csv_file("./data/route_stops.csv")
    stops = read_csv_file("./data/stops.csv")

    print(f"Found {len(routes)} routes")
    print(f"Found {len(route_stops)} route stops")
    print(f"Found {len(stops)} stops")

    # Generate route schedules
    print("\nGenerating route schedules...")
    route_schedules = generate_route_schedules(routes)
    print(f"Generated {len(route_schedules)} route schedules")

    # Generate stop schedules
    print("\nGenerating stop schedules...")
    stop_schedules = generate_stop_schedules(routes, route_stops, route_schedules)
    print(f"Generated {len(stop_schedules)} stop schedules")

    # Write to files
    print("\nWriting to files...")

    # Route schedules CSV
    route_schedule_fields = [
        "route_name",
        "departure_time",
        "service_days",
        "valid_from",
        "valid_until",
        "is_active",
    ]
    write_csv_file(
        "./data/route_schedules_generated.csv", route_schedules, route_schedule_fields
    )

    # Stop schedules CSV
    stop_schedule_fields = [
        "route_name",
        "stop_code",
        "arrival_time",
        "is_active",
        "created_at",
    ]
    write_csv_file(
        "./data/stop_schedules_generated.csv", stop_schedules, stop_schedule_fields
    )

    print("\nDone!")
    print("Route schedules saved to: route_schedules_generated.csv")
    print("Stop schedules saved to: stop_schedules_generated.csv")

    # Show some sample data
    print("\nSample route schedule:")
    for i, rs in enumerate(route_schedules[:3]):
        print(f"  Route {rs['route_name']} at {rs['departure_time']}")

    print("\nSample stop schedule:")
    for i, ss in enumerate(stop_schedules[:5]):
        print(
            f"  Route {ss['route_name']}, Stop {ss['stop_code']} at {ss['arrival_time']}"
        )


if __name__ == "__main__":
    main()
