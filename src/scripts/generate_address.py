import csv
import os
import sys
import time
from math import atan2, cos, radians, sin, sqrt

import requests

# Multiple Overpass API mirrors for redundancy
OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in meters between two coordinates using Haversine formula."""
    R = 6371000
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def find_buildings_with_addresses_overpass(
    latitude, longitude, radius, timeout=15, max_retries=2
):
    """Search for buildings with addresses using Overpass API with multiple mirrors."""
    query = f"""
    [out:json][timeout:{timeout}];
    (
      node(around:{radius},{latitude},{longitude})["addr:housenumber"];
      way(around:{radius},{latitude},{longitude})["addr:housenumber"];
    );
    out center;
    """

    for i, endpoint in enumerate(OVERPASS_ENDPOINTS[:max_retries]):
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                timeout=timeout,
                headers={"User-Agent": "CSVAddressFinder/1.0"},
            )
            response.raise_for_status()
            data = response.json()

            buildings = []
            for element in data.get("elements", []):
                tags = element.get("tags", {})

                if element["type"] == "node":
                    elem_lat = element["lat"]
                    elem_lon = element["lon"]
                elif element["type"] == "way" and "center" in element:
                    elem_lat = element["center"]["lat"]
                    elem_lon = element["center"]["lon"]
                else:
                    continue

                distance = calculate_distance(latitude, longitude, elem_lat, elem_lon)

                building = {
                    "lat": elem_lat,
                    "lon": elem_lon,
                    "distance": round(distance, 1),
                    "house_number": tags.get("addr:housenumber", ""),
                    "street": tags.get("addr:street", ""),
                    "city": tags.get("addr:city", ""),
                    "postcode": tags.get("addr:postcode", ""),
                }
                buildings.append(building)

            buildings.sort(key=lambda x: x["distance"])
            return buildings

        except Exception:
            continue

    return None


def get_address_from_nominatim(latitude, longitude):
    """Get address using Nominatim reverse geocoding."""
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "jsonv2",
        "accept-language": "ru",
        "addressdetails": 1,
        "zoom": 18,
    }
    headers = {"User-Agent": "CSVAddressFinder/1.0"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        address = data.get("address", {})

        # Get coordinates of found address
        found_lat = float(data.get("lat", latitude))
        found_lon = float(data.get("lon", longitude))
        distance = calculate_distance(latitude, longitude, found_lat, found_lon)

        # Build address string
        parts = []
        street = address.get("road", "")
        house = address.get("house_number", "")

        if street and house:
            parts.append(f"{street}, {house}")
        elif street:
            parts.append(street)

        city = address.get("city") or address.get("town") or address.get("village", "")
        if city and city != "Вятские Поляны":
            parts.append(city)

        address_str = ", ".join(parts) if parts else data.get("display_name", "")

        return {
            "address": address_str,
            "distance": round(distance, 1),
            "house_number": house,
        }

    except Exception as e:
        return {"address": f"Ошибка: {str(e)}", "distance": None, "house_number": ""}


def find_address_for_coordinates(
    latitude, longitude, start_radius=20, max_radius=200, radius_step=40, delay=1.5
):
    """
    Find nearest address for given coordinates with ITERATIVE expanding radius search.
    Returns dict with address, distance, and house_number.
    """
    current_radius = start_radius

    print(f"  🔍 Поиск с радиусом {start_radius}м → {max_radius}м")

    # Try Overpass with expanding radius - ITERATIVE APPROACH
    while current_radius <= max_radius:
        print(f"    Радиус {current_radius}м...", end=" ")

        buildings = find_buildings_with_addresses_overpass(
            latitude, longitude, current_radius
        )

        if buildings is None:
            # Overpass failed, use Nominatim fallback
            print("Overpass недоступен")
            break

        if buildings:
            nearest = buildings[0]
            print(f"✓ Найдено! Расстояние: {nearest['distance']}м")

            # Build address string
            parts = []
            if nearest["street"] and nearest["house_number"]:
                parts.append(f"{nearest['street']}, {nearest['house_number']}")
            elif nearest["street"]:
                parts.append(nearest["street"])

            if nearest["city"]:
                parts.append(nearest["city"])

            address_str = ", ".join(parts) if parts else "Адрес найден (без деталей)"

            return {
                "address": address_str,
                "distance": nearest["distance"],
                "house_number": nearest["house_number"],
            }
        else:
            print("Ничего", end=", ")

        current_radius += radius_step
        time.sleep(delay)

    # Fallback to Nominatim
    print("    → Используем Nominatim...")
    time.sleep(delay)
    return get_address_from_nominatim(latitude, longitude)


def process_csv_file(input_file, output_file=None, delay=1.5):
    """
    Read CSV file, find addresses for coordinates, save to new CSV with address and address_dist columns.

    Args:
        input_file (str): Path to input CSV file
        output_file (str): Path to output CSV file (default: overwrites input)
        delay (float): Delay between API requests in seconds
    """
    if not os.path.exists(input_file):
        print(f"❌ Файл не найден: {input_file}")
        return

    if output_file is None:
        output_file = input_file

    print(f"📂 Входной файл: {input_file}")
    print(f"📂 Выходной файл: {output_file}\n")

    # Read CSV
    with open(input_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames)  # ty:ignore[invalid-argument-type]

    if not rows:
        print("❌ CSV файл пустой")
        return

    print(f"✓ Прочитано строк: {len(rows)}")
    print(f"✓ Колонки: {', '.join(fieldnames)}\n")

    lat_col, lon_col = "latitude", "longitude"
    # lat_col, lon_col = lon_col, lat_col # TODO: Assume mixed order!

    # Add new columns if they don't exist
    if "address" not in fieldnames:
        fieldnames.append("address")
    if "address_dist" not in fieldnames:
        fieldnames.append("address_dist")

    # Process each row
    print("=" * 70)
    print("ОБРАБОТКА КООРДИНАТ (ИТЕРАТИВНЫЙ ПОИСК)")
    print("=" * 70)

    success_count = 0
    with_house_number = 0

    for i, row in enumerate(rows, 1):
        try:
            lat = float(row[lat_col])
            lon = float(row[lon_col])

            print(f"\n[{i}/{len(rows)}] Координаты: {lat}, {lon}")

            # Use iterative search that returns dict with address and distance
            result = find_address_for_coordinates(lat, lon, delay=delay)

            row["address"] = result["address"]
            row["address_dist"] = (
                result["distance"] if result["distance"] is not None else ""
            )
            row["longitude"] = lon
            row["latitude"] = lat

            if result["house_number"]:
                with_house_number += 1
                print(
                    f"  ✓ Адрес с домом: {result['address']} (расстояние: {result['distance']}м)"
                )
            else:
                print(f"  ⚠ Адрес без номера дома: {result['address']}")

            success_count += 1

            # Progress delay
            if i < len(rows):
                time.sleep(delay)

        except (ValueError, KeyError) as e:
            print(f"  ❌ Ошибка в строке {i}: {e}")
            row["address"] = None
            row["address_dist"] = 0

    # Write output CSV
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'=' * 70}")
    print(f"✓ ГОТОВО! Результаты сохранены в: {output_file}")
    print(f"{'=' * 70}")
    print(f"Обработано: {len(rows)}")
    print(f"Успешно: {success_count}")
    print(f"С номером дома: {with_house_number}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    print("=" * 70)
    print("CSV ADDRESS FINDER - Поиск адресов по координатам")
    print("=" * 70)
    print()

    input_csv = "./data/stops.csv"
    output_csv = None

    if len(sys.argv) >= 2:
        input_csv = sys.argv[1]
        output_csv = sys.argv[2] if len(sys.argv) > 2 else None

    process_csv_file(input_csv, output_csv, delay=1.5)
