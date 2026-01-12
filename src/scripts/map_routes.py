import csv
from collections import defaultdict

import folium
from folium import plugins


def read_stops(filename):
    """Read stops data from CSV file"""
    stops = {}
    with open(filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Strip whitespace from all values
                row = {
                    k.strip(): v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                }
                stops[row["code"]] = {
                    "name": row["name"],
                    "lat": float(row["latitude"]),
                    "lon": float(row["longitude"]),
                    "is_active": row["is_active"],
                    "side": row["side_identifier"],
                }
            except (KeyError, ValueError) as e:
                print(f"Error reading stop {row.get('code', 'unknown')}: {e}")
                continue
    return stops


def read_routes(filename):
    """Read routes data from CSV file"""
    routes = {}
    with open(filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Strip whitespace from all values
                row = {
                    k.strip(): v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                }
                route_num = int(row["route_number"])

                # Handle the color field - remove quotes if present
                color = row["color"]
                if color.startswith('"') and color.endswith('"'):
                    color = color[1:-1]  # Remove surrounding quotes

                routes[route_num] = {
                    "origin": row["origin_stop_code"],
                    "destination": row["destination_stop_code"],
                    "description": row["description"],
                    "color": color,  # Store cleaned color
                    "is_active": int(row["is_active"]) == 1,
                }
            except (KeyError, ValueError) as e:
                print(f"Error reading route {row.get('route_number', 'unknown')}: {e}")
                continue
    return routes


def read_route_stops(filename):
    """Read route stops sequence from CSV file"""
    route_sequences = defaultdict(list)
    with open(filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Strip whitespace from all values
                row = {
                    k.strip(): v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                }
                route_num = int(row["route_number"])
                stop_code = row["stop_code"]
                stop_order = int(row["stop_order"])
                route_sequences[route_num].append((stop_order, stop_code))
            except (KeyError, ValueError) as e:
                print(f"Error reading route stop: {e}")
                continue

    # Sort each route's stops by order
    for route_num in route_sequences:
        route_sequences[route_num].sort(key=lambda x: x[0])
        # Get just the stop codes in order
        route_sequences[route_num] = [
            stop_code for _, stop_code in route_sequences[route_num]
        ]

    return route_sequences


def create_map(stops, routes, route_sequences):
    """Create Folium map with routes and stops"""

    # Calculate center of map based on all stops
    if stops:
        avg_lat = sum(s["lat"] for s in stops.values()) / len(stops)
        avg_lon = sum(s["lon"] for s in stops.values()) / len(stops)
        print(f"Map center: {avg_lat:.6f}, {avg_lon:.6f}")
    else:
        avg_lat, avg_lon = 56.23, 51.07  # Fallback center

    # Create base map
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13, tiles="CartoDB positron")

    # Add fullscreen button
    plugins.Fullscreen().add_to(m)

    print(f"\nFound {len(route_sequences)} routes with stop sequences")

    # Create feature groups for better layer control
    route_layer = folium.FeatureGroup(name="Routes", show=True)
    stop_layer = folium.FeatureGroup(name="Stops", show=True)

    # Draw routes first (so they're underneath stops)
    print("\n=== DRAWING ROUTES ===")

    for route_num in sorted(route_sequences.keys()):
        if route_num not in routes:
            print(f"Route {route_num}: Skipping - no route info")
            continue

        route_info = routes[route_num]
        if not route_info["is_active"]:
            print(f"Route {route_num}: Skipping - inactive")
            continue

        stop_codes = route_sequences[route_num]
        if not stop_codes:
            print(f"Route {route_num}: Skipping - no stops")
            continue

        print(f"\nRoute {route_num}:")
        print(f"  From: {route_info['origin']} to {route_info['destination']}")
        print(f"  Stops: {len(stop_codes)}")

        # Get coordinates for all stops in this route
        route_coords = []
        valid_stops = 0

        for stop_code in stop_codes:
            if stop_code in stops:
                stop = stops[stop_code]
                route_coords.append([stop["lat"], stop["lon"]])
                valid_stops += 1
            else:
                print(f"  Warning: Stop '{stop_code}' not found in stops database")

        if valid_stops < 2:
            print(f"  Error: Only {valid_stops} valid stops, need at least 2")
            continue

        print(f"  Valid coordinates: {valid_stops}/{len(stop_codes)}")

        # Process color
        color = route_info["color"]
        print(f"  Raw color from CSV: '{color}'")

        # Clean the color string
        # Remove any quotes
        color = color.replace('"', "").replace("'", "")

        # Remove # if present
        if color.startswith("#"):
            color = color[1:]

        # Remove alpha channel (last 2 characters) if present
        if len(color) == 8:  # RRGGBBAA format
            color = color[:6]  # Keep only RRGGBB

        print(f"  Cleaned color: #{color}")

        # Create the route line
        try:
            # Create a PolyLine for the route
            line = folium.PolyLine(
                locations=route_coords,
                color=f"#{color}",
                weight=6,
                opacity=0.8,
                popup=folium.Popup(
                    f"<b>Route {route_num}</b><br>"
                    f"From: {route_info['origin']}<br>"
                    f"To: {route_info['destination']}<br>"
                    f"Stops: {len(stop_codes)}<br>"
                    f"Color: #{color}",
                    max_width=250,
                ),
                tooltip=f"Route {route_num}: {route_info['origin']} → {route_info['destination']}",
                line_cap="round",
                line_join="round",
            )
            line.add_to(route_layer)
            print("  ✓ Route line added successfully")

            # Add start and end markers
            if route_coords:
                # Start marker
                folium.CircleMarker(
                    location=route_coords[0],
                    radius=8,
                    color="green",
                    fill=True,
                    fill_color="green",
                    fill_opacity=1.0,
                    weight=2,
                    popup=f"Start: {route_info['origin']}",
                ).add_to(route_layer)

                # End marker
                folium.CircleMarker(
                    location=route_coords[-1],
                    radius=8,
                    color="red",
                    fill=True,
                    fill_color="red",
                    fill_opacity=1.0,
                    weight=2,
                    popup=f"End: {route_info['destination']}",
                ).add_to(route_layer)

        except Exception as e:
            print(f"  ✗ Error drawing route: {e}")

    # Draw stops
    print("\n=== DRAWING STOPS ===")

    stop_count = 0
    for stop_code, stop_info in stops.items():
        # Find which routes use this stop
        routes_for_stop = []
        for route_num, stop_list in route_sequences.items():
            if route_num in routes and routes[route_num]["is_active"]:
                if stop_code in stop_list:
                    routes_for_stop.append(str(route_num))

        if routes_for_stop:
            stop_count += 1

            # Create a colored circle for the stop
            folium.CircleMarker(
                location=[stop_info["lat"], stop_info["lon"]],
                radius=7,
                color="blue",
                fill=True,
                fill_color="lightblue",
                fill_opacity=0.8,
                weight=2,
                popup=folium.Popup(
                    f"<b>{stop_info['name']}</b><br>"
                    f"Code: {stop_code}<br>"
                    f"Routes: {', '.join(sorted(routes_for_stop))}<br>"
                    f"Lat: {stop_info['lat']:.6f}<br>"
                    f"Lon: {stop_info['lon']:.6f}",
                    max_width=250,
                ),
                tooltip=f"{stop_info['name']} (Routes: {', '.join(sorted(routes_for_stop))})",
            ).add_to(stop_layer)

    print(f"✓ Added {stop_count} stops to the map")

    # Add layers to map
    route_layer.add_to(m)
    stop_layer.add_to(m)

    # Add layer control
    folium.LayerControl(collapsed=False).add_to(m)

    # Add minimap
    minimap = plugins.MiniMap()
    m.add_child(minimap)

    # Add a simple legend
    legend_html = """
    <div style="
        position: fixed;
        bottom: 50px;
        left: 50px;
        width: 180px;
        height: auto;
        background-color: white;
        border: 2px solid grey;
        z-index: 9999;
        font-size: 12px;
        padding: 10px;
        border-radius: 5px;
        box-shadow: 3px 3px 5px rgba(0,0,0,0.2);">
        <b>Map Legend</b><br>
        <hr style="margin: 5px 0;">
        <div style="display: flex; align-items: center; margin: 3px 0;">
            <div style="width: 20px; height: 10px; background-color: green; margin-right: 5px;"></div>
            Route Start
        </div>
        <div style="display: flex; align-items: center; margin: 3px 0;">
            <div style="width: 20px; height: 10px; background-color: red; margin-right: 5px;"></div>
            Route End
        </div>
        <div style="display: flex; align-items: center; margin: 3px 0;">
            <div style="width: 12px; height: 12px; background-color: lightblue;
                 border: 2px solid blue; border-radius: 50%; margin-right: 5px;"></div>
            Bus Stop
        </div>
        <div style="margin-top: 8px; font-size: 11px; color: #666;">
            Click on lines or markers for info
        </div>
    </div>
    """

    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def main():
    print("=" * 70)
    print("BUS ROUTE VISUALIZATION TOOL")
    print("=" * 70)

    # Read data
    print("\n[1/3] Reading data files...")

    try:
        stops = read_stops("./data/stops_real.csv")
        print(f"   ✓ Loaded {len(stops)} stops")
    except Exception as e:
        print(f"   ✗ Failed to load stops.csv: {e}")
        return

    try:
        routes = read_routes("./data/routes_real.csv")
        print(f"   ✓ Loaded {len(routes)} routes")
    except Exception as e:
        print(f"   ✗ Failed to load routes.csv: {e}")
        return

    try:
        route_sequences = read_route_stops("./data/route_stops_real.csv")
        print(f"   ✓ Loaded {len(route_sequences)} route sequences")
    except Exception as e:
        print(f"   ✗ Failed to load route_stops.csv: {e}")
        return

    # Check data consistency
    print("\n[2/3] Checking data consistency...")

    # Check for routes without sequence
    routes_without_sequence = [r for r in routes if r not in route_sequences]
    if routes_without_sequence:
        print(f"   ⚠  Routes without stop sequence: {routes_without_sequence}")

    # Check for sequences without route info
    sequences_without_route = [s for s in route_sequences if s not in routes]
    if sequences_without_route:
        print(f"   ⚠  Stop sequences without route info: {sequences_without_route}")

    # Count active routes
    active_routes = [r for r, info in routes.items() if info["is_active"]]
    print(f"   ✓ Active routes: {len(active_routes)}/{len(routes)}")

    # Create map
    print("\n[3/3] Creating map visualization...")
    print("-" * 70)

    m = create_map(stops, routes, route_sequences)

    # Save the map
    output_file = "bus_routes_visualization.html"
    m.save(output_file)

    print("\n" + "=" * 70)
    print("✅ MAP GENERATION COMPLETE!")
    print("=" * 70)

    print(f"\n📁 Output file: {output_file}")
    print("\n🔍 TROUBLESHOOTING TIPS:")
    print("   1. Open the HTML file in Chrome/Firefox (not Internet Explorer)")
    print("   2. Zoom in/out using mouse wheel or +/- buttons")
    print("   3. Click on colored lines to see route information")
    print("   4. Click on blue circles to see stop information")
    print("   5. Use the layer control (top-right) to show/hide routes or stops")
    print("\n   If lines still don't appear:")
    print("   - Check browser console for errors (F12 → Console)")
    print("   - Ensure all CSV files are in correct format")
    print("   - Verify coordinates are within reasonable range")

    # Show sample coordinates
    print("\n📍 SAMPLE COORDINATES (first 3 stops):")
    print("-" * 40)
    for i, (stop_code, stop_info) in enumerate(list(stops.items())[:3]):
        print(f"   {stop_code}: {stop_info['name']}")
        print(f"      Latitude: {stop_info['lat']}")
        print(f"      Longitude: {stop_info['lon']}")

    print("\n🚀 Ready! Open the HTML file in your browser to view the map.")


if __name__ == "__main__":
    main()
