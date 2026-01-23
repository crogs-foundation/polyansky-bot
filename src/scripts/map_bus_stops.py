import csv

import folium
from folium.features import DivIcon
from folium.plugins import MarkerCluster, MiniMap


def create_bus_stop_map(csv_file="stops.csv", output_file="bus_stops_map.html"):
    """
    Create an interactive map with all bus stops from CSV file.

    Args:
        csv_file: Path to the CSV file containing bus stops data
        output_file: Path to save the HTML map file
    """

    # Read bus stops data
    bus_stops = []

    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            # Detect delimiter (checking for comma or semicolon)
            reader = csv.DictReader(f, delimiter=",")

            # Clean up column names (strip whitespace)
            fieldnames = [field.strip() for field in reader.fieldnames or ""]
            reader = csv.DictReader(f, delimiter=",", fieldnames=fieldnames)

            for row in reader:
                # Clean row values
                cleaned_row = {}
                print(row)
                for key, value in row.items():
                    cleaned_key = key.strip()
                    cleaned_value = value.strip() if value else ""
                    cleaned_row[cleaned_key] = cleaned_value

                bus_stops.append(cleaned_row)

        print(f"Successfully loaded {len(bus_stops)} bus stops from {csv_file}")

    except FileNotFoundError:
        print(f"Error: File {csv_file} not found!")
        return
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return

    # Check required columns
    required_columns = ["code", "name", "latitude", "longitude"]
    available_columns = list(bus_stops[0].keys()) if bus_stops else []
    missing_columns = [col for col in required_columns if col not in available_columns]

    if missing_columns:
        print(f"Error: Missing required columns: {missing_columns}")
        print(f"Available columns: {available_columns}")
        return

    if not bus_stops:
        print("Error: No bus stops found in CSV file")
        return

    # Calculate map center (average of all coordinates)
    try:
        latitudes = [float(stop["latitude"]) for stop in bus_stops if stop["latitude"]]
        longitudes = [float(stop["longitude"]) for stop in bus_stops if stop["longitude"]]

        if not latitudes or not longitudes:
            print("Error: No valid coordinates found")
            return

        center_lat = sum(latitudes) / len(latitudes)
        center_lon = sum(longitudes) / len(longitudes)

    except ValueError as e:
        print(f"Error parsing coordinates: {e}")
        # Try to find first valid coordinate
        for stop in bus_stops:
            try:
                center_lat = float(stop["latitude"])
                center_lon = float(stop["longitude"])
                break
            except (ValueError, KeyError):
                continue
        else:
            print("Could not find any valid coordinates")
            return

    # Create the map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="OpenStreetMap",
        control_scale=True,
        prefer_canvas=True,  # Better for many markers
    )

    # Add a minimap for navigation
    minimap = MiniMap()
    m.add_child(minimap)

    # Create marker clusters for better performance with many markers
    marker_cluster = MarkerCluster(
        name="Bus Stops",
        overlay=True,
        control=True,
        options={"maxClusterRadius": 50, "disableClusteringAtZoom": 15},
    ).add_to(m)

    # Create a separate layer for stop codes text
    text_layer = folium.FeatureGroup(
        name="Stop Codes", overlay=True, control=True
    ).add_to(m)

    # Define color scheme for different side identifiers
    side_colors = {
        "A": "red",
        "B": "blue",
        "C": "green",
        "D": "purple",
        "E": "orange",
        "F": "darkred",
        "G": "darkblue",
        "H": "darkgreen",
        "I": "cadetblue",
        "J": "pink",
        "K": "lightblue",
        "L": "lightgreen",
        "M": "gray",
        "N": "black",
        "O": "white",
        "P": "beige",
    }

    # Default colors for other identifiers or no identifier
    default_colors = [
        "red",
        "blue",
        "green",
        "purple",
        "orange",
        "darkred",
        "darkblue",
        "darkgreen",
        "cadetblue",
        "pink",
    ]

    # Track used colors for consistency
    used_colors = {}

    # Add markers for each bus stop
    for stop in bus_stops:
        try:
            lat = float(stop["latitude"])
            lon = float(stop["longitude"])

            # Skip invalid coordinates
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                print(
                    f"Warning: Invalid coordinates for stop {stop.get('code', 'Unknown')}: ({lat}, {lon})"
                )
                continue

            # Get stop information
            code = stop.get("code", "N/A")
            name = stop.get("name", "N/A")
            side_identifier = stop.get("side_identifier", "").strip()
            address = stop.get("address", "N/A")
            address_dist = stop.get("address_dist", "N/A")
            is_active = stop.get("is_active", "True")

            # Determine marker color based on side identifier
            if side_identifier and side_identifier.upper() in side_colors:
                color = side_colors[side_identifier.upper()]
            elif side_identifier:
                # For custom side identifiers, assign a consistent color
                if side_identifier not in used_colors:
                    # Use modulo to cycle through default colors
                    color_idx = len(used_colors) % len(default_colors)
                    used_colors[side_identifier] = default_colors[color_idx]
                color = used_colors[side_identifier]
            else:
                color = "gray"  # No side identifier

            # Create popup content
            popup_html = f"""
            <div style="font-family: Arial, sans-serif; min-width: 200px;">
                <h4 style="margin: 0 0 10px 0; color: #2c3e50; border-bottom: 2px solid {color}; padding-bottom: 5px;">
                    {name}
                </h4>
                <p style="margin: 5px 0;">
                    <strong>Code:</strong> {code}<br>
                    <strong>Side:</strong> {side_identifier if side_identifier else "N/A"}<br>
                    <strong>Status:</strong> {"Active" if is_active.lower() == "true" else "Inactive"}<br>
                    <strong>Address:</strong> {address}<br>
                    <strong>Distance:</strong> {address_dist}<br>
                </p>
                <p style="margin: 5px 0; font-size: 0.9em; color: #666;">
                    Coordinates: {lat:.6f}, {lon:.6f}
                </p>
            </div>
            """

            # Create a circle marker for the stop location
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.8,
                weight=2,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"{code}: {name}",
            ).add_to(marker_cluster)

            # Add stop code text next to the marker (slightly offset)
            # Calculate offset based on latitude to avoid overlapping
            offset_lat = lat + 0.00015  # Small offset to place text above marker

            # Create text marker with the stop code
            folium.Marker(
                location=[offset_lat, lon],
                icon=DivIcon(
                    icon_size=(100, 36),
                    icon_anchor=(50, 18),
                    html=f'<div style="font-size: 10pt; font-weight: bold; color: {color}; background-color: white; border: 1px solid {color}; border-radius: 3px; padding: 2px 4px; text-align: center; white-space: nowrap;">{code}</div>',
                ),
                tooltip=f"Stop code: {code}",
            ).add_to(text_layer)

        except (ValueError, KeyError) as e:
            print(f"Warning: Could not process stop {stop.get('code', 'Unknown')}: {e}")
            continue

    # Add layer control
    folium.LayerControl().add_to(m)

    # Add fullscreen button
    folium.plugins.Fullscreen().add_to(m)

    # Add measure control
    folium.plugins.MeasureControl(
        position="topleft",
        primary_length_unit="meters",
        secondary_length_unit="kilometers",
    ).add_to(m)

    # Add a title to the map
    title_html = """
    <div style="position: fixed;
                top: 10px; left: 50px; width: 350px; height: 60px;
                background-color: white; border:2px solid grey; border-radius: 5px;
                z-index: 9999; font-size: 14px; padding: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.5);">
        <h3 style="margin: 0; text-align: center;">
            🚏 Bus Stops Map
        </h3>
        <p style="margin: 0; font-size: 12px; text-align: center;">
            Total: {} stops • Toggle layers in top-right menu
        </p>
    </div>
    """.format(len(bus_stops))
    m.get_root().html.add_child(folium.Element(title_html))

    # Save the map
    try:
        m.save(output_file)
        print(f"\n✅ Map successfully created and saved to: {output_file}")
        print(f"   Total bus stops plotted: {len(bus_stops)}")

        # Show some statistics
        active_stops = sum(
            1 for stop in bus_stops if stop.get("is_active", "").lower() == "true"
        )
        inactive_stops = sum(
            1 for stop in bus_stops if stop.get("is_active", "").lower() == "false"
        )

        print("\n📊 Statistics:")
        print(f"   • Active stops: {active_stops}")
        print(f"   • Inactive stops: {inactive_stops}")

        # Count stops by side identifier
        side_counts = {}
        for stop in bus_stops:
            side = stop.get("side_identifier", "").strip()
            if side:
                side_counts[side] = side_counts.get(side, 0) + 1

        if side_counts:
            print("\n🚏 Stops by side identifier:")
            for side, count in sorted(side_counts.items()):
                print(f"   • Side {side}: {count} stops")

        # Instructions for opening the map
        print("\n🌍 To view the map:")
        print(f"   1. Open {output_file} in your web browser")
        print("   2. Or run: python -m http.server 8000")
        print(f"      Then open: http://localhost:8000/{output_file}")

    except Exception as e:
        print(f"Error saving map: {e}")


def main():
    """Main function to run the script."""
    import sys

    print("=" * 50)
    print("🚌 Bus Stop Map Generator")
    print("=" * 50)

    # Get input file from command line or use default
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = "./data/stops.csv"

    # Get output file from command line or use default
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        output_file = "bus_stops_map.html"

    print(f"\n📂 Input file: {csv_file}")
    print(f"🗺️  Output file: {output_file}")
    print("-" * 50)

    create_bus_stop_map(csv_file, output_file)

    print("\n" + "=" * 50)
    print("✨ Map generation complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
