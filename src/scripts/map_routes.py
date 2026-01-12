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
                row = {
                    k.strip(): v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                }
                name = row["name"]

                # Handle the color field - remove quotes if present
                color = row["color"]
                if color.startswith('"') and color.endswith('"'):
                    color = color[1:-1]

                routes[name] = {
                    "origin": row["origin_stop_code"],
                    "destination": row["destination_stop_code"],
                    "description": row["description"],
                    "color": color,
                    "is_active": row["is_active"] == "True",
                }
            except (KeyError, ValueError) as e:
                print(f"Error reading route {row.get('name', 'unknown')}: {e}")
                continue
    return routes


def read_route_stops(filename):
    """Read route stops sequence from CSV file"""
    route_sequences = defaultdict(list)
    with open(filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row = {
                    k.strip(): v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                }
                route_name = row["route_name"]
                stop_code = row["stop_code"]
                stop_order = int(row["stop_order"])
                route_sequences[route_name].append((stop_order, stop_code))
            except (KeyError, ValueError) as e:
                print(f"Error reading route stop: {e}")
                continue

    # Sort each route's stops by order
    for route_name in route_sequences:
        route_sequences[route_name].sort(key=lambda x: x[0])
        route_sequences[route_name] = [
            stop_code for _, stop_code in route_sequences[route_name]
        ]

    return route_sequences


def clean_color(color: str) -> str:
    """Clean and normalize color hex code"""
    # Remove quotes
    color = color.replace('"', "").replace("'", "")

    # Remove # if present
    if color.startswith("#"):
        color = color[1:]

    # Remove alpha channel (last 2 chars) if present
    if len(color) == 8:  # RRGGBBAA format
        color = color[:6]  # Keep only RRGGBB

    return color


def create_map(stops, routes, route_sequences):
    """Create Folium map with routes and stops with individual route toggles"""

    # Calculate center of map
    if stops:
        avg_lat = sum(s["lat"] for s in stops.values()) / len(stops)
        avg_lon = sum(s["lon"] for s in stops.values()) / len(stops)
        print(f"Map center: {avg_lat:.6f}, {avg_lon:.6f}")
    else:
        avg_lat, avg_lon = 56.23, 51.07  # Fallback

    # Create base map
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13, tiles="CartoDB positron")

    # Add fullscreen button
    plugins.Fullscreen().add_to(m)

    print(f"\nFound {len(route_sequences)} routes with stop sequences")

    # Create stops layer (always visible)
    stop_layer = folium.FeatureGroup(name="🚏 All Bus Stops", show=True, overlay=True)

    # Dictionary to track which routes use each stop
    stops_to_routes = defaultdict(list)

    print("\n=== DRAWING ROUTES ===")

    # Create separate FeatureGroup for each route (enables individual toggles)
    # Sort alphabetically as strings (not numerically)
    sorted_route_nums = sorted(route_sequences.keys())

    route_layers = {}

    for route_num in sorted_route_nums:
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

        # Track stops for this route
        for stop_code in stop_codes:
            if stop_code in stops:
                stops_to_routes[stop_code].append(route_num)

        # Get coordinates for all stops in this route
        route_coords = []
        valid_stops = 0

        for stop_code in stop_codes:
            if stop_code in stops:
                stop = stops[stop_code]
                route_coords.append([stop["lat"], stop["lon"]])
                valid_stops += 1
            else:
                print(f"  Warning: Stop '{stop_code}' not found")

        if valid_stops < 2:
            print(f"  Error: Only {valid_stops} valid stops, need at least 2")
            continue

        print(f"  Valid coordinates: {valid_stops}/{len(stop_codes)}")

        # Clean color
        color = clean_color(route_info["color"])
        print(f"  Color: #{color}")

        # Create separate layer for this route with unique ID
        route_layer_name = f"🚌 Route {route_num}"
        route_layer = folium.FeatureGroup(
            name=route_layer_name, show=True, overlay=True, control=True
        )
        route_layers[route_num] = route_layer

        try:
            # Create the route line
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
                    f"<div style='width:50px;height:20px;background-color:#{color};border:1px solid black;'></div>",
                    max_width=250,
                ),
                tooltip=f"Route {route_num}: {route_info['origin']} → {route_info['destination']}",
                line_cap="round",
                line_join="round",
            )
            line.add_to(route_layer)

            # Add direction arrow markers at intervals
            if len(route_coords) >= 3:
                plugins.PolyLineTextPath(
                    line,
                    "    ►    ",
                    repeat=True,
                    offset=8,
                    attributes={"fill": f"#{color}", "font-size": "18"},
                ).add_to(route_layer)

            # Start marker (green circle)
            if route_coords:
                folium.CircleMarker(
                    location=route_coords[0],
                    radius=8,
                    color="green",
                    fill=True,
                    fill_color="lightgreen",
                    fill_opacity=1.0,
                    weight=3,
                    popup=f"<b>Route {route_num} Start</b><br>{route_info['origin']}",
                    tooltip=f"Start: {route_info['origin']}",
                ).add_to(route_layer)

                # End marker (red circle)
                folium.CircleMarker(
                    location=route_coords[-1],
                    radius=8,
                    color="red",
                    fill=True,
                    fill_color="lightcoral",
                    fill_opacity=1.0,
                    weight=3,
                    popup=f"<b>Route {route_num} End</b><br>{route_info['destination']}",
                    tooltip=f"End: {route_info['destination']}",
                ).add_to(route_layer)

            # Add route layer to map
            route_layer.add_to(m)
            print("  ✓ Route added successfully")

        except Exception as e:
            print(f"  ✗ Error drawing route: {e}")

    # Draw all stops on the stop layer
    print("\n=== DRAWING STOPS ===")

    stop_count = 0
    for stop_code, stop_info in stops.items():
        routes_for_stop = [str(r) for r in stops_to_routes.get(stop_code, [])]

        if routes_for_stop:
            stop_count += 1

            # Create popup with route info
            routes_html = "<br>".join(
                [
                    f"<span style='color:#{clean_color(routes[r]['color'])};font-weight:bold;'>Route {r}</span>"
                    for r in routes_for_stop
                    if r in routes
                ]
            )

            folium.CircleMarker(
                location=[stop_info["lat"], stop_info["lon"]],
                radius=6,
                color="darkblue",
                fill=True,
                fill_color="lightblue",
                fill_opacity=0.9,
                weight=2,
                popup=folium.Popup(
                    f"<b>{stop_info['name']}</b><br>"
                    f"<small>Code: {stop_code}</small><br>"
                    f"<hr style='margin:5px 0;'>"
                    f"<b>Routes:</b><br>{routes_html}",
                    max_width=300,
                ),
                tooltip=f"{stop_info['name']} ({', '.join(sorted(routes_for_stop))})",
            ).add_to(stop_layer)

    print(f"✓ Added {stop_count} stops to the map")

    # Add stop layer to map
    stop_layer.add_to(m)

    # Add layer control with all routes individually toggleable
    folium.LayerControl(collapsed=False, position="topright", autoZIndex=True).add_to(m)

    # Add minimap
    minimap = plugins.MiniMap(toggle_display=True)
    m.add_child(minimap)

    # Enhanced legend with route colors
    route_legend_items = ""
    for route_num in sorted_route_nums:
        if route_num in routes and routes[route_num]["is_active"]:
            color = clean_color(routes[route_num]["color"])
            route_legend_items += f"""
            <div style="display: flex; align-items: center; margin: 3px 0;">
                <div style="width: 30px; height: 4px; background-color: #{color}; margin-right: 8px;"></div>
                <span style="font-size: 11px;">Route {route_num}</span>
            </div>
            """

    legend_html = f"""
    <div style="
        position: fixed;
        bottom: 50px;
        left: 50px;
        width: 200px;
        max-height: 400px;
        overflow-y: auto;
        background-color: white;
        border: 2px solid grey;
        z-index: 9999;
        font-size: 12px;
        padding: 10px;
        border-radius: 5px;
        box-shadow: 3px 3px 5px rgba(0,0,0,0.2);">
        <b>Map Legend</b><br>
        <hr style="margin: 5px 0;">

        <div style="margin-bottom: 8px;">
            <b style="font-size: 11px;">Route Controls:</b>
            <div style="display: flex; gap: 5px; margin-top: 5px;">
                <button id="selectAllRoutes" style="
                    flex: 1;
                    padding: 4px 8px;
                    font-size: 10px;
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    cursor: pointer;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    ✓ All
                </button>
                <button id="deselectAllRoutes" style="
                    flex: 1;
                    padding: 4px 8px;
                    font-size: 10px;
                    background-color: #f44336;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    cursor: pointer;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    ✗ None
                </button>
            </div>
        </div>

        <hr style="margin: 5px 0;">

        <div style="display: flex; align-items: center; margin: 3px 0;">
            <div style="width: 12px; height: 12px; background-color: lightgreen;
                 border: 3px solid green; border-radius: 50%; margin-right: 8px;"></div>
            Route Start
        </div>
        <div style="display: flex; align-items: center; margin: 3px 0;">
            <div style="width: 12px; height: 12px; background-color: lightcoral;
                 border: 3px solid red; border-radius: 50%; margin-right: 8px;"></div>
            Route End
        </div>
        <div style="display: flex; align-items: center; margin: 3px 0;">
            <div style="width: 12px; height: 12px; background-color: lightblue;
                 border: 2px solid darkblue; border-radius: 50%; margin-right: 8px;"></div>
            Bus Stop
        </div>

        <hr style="margin: 8px 0;">
        <b style="font-size: 11px;">Routes:</b>
        <div style="margin-top: 5px;">
            {route_legend_items}
        </div>

        <hr style="margin: 8px 0;">
        <div style="font-size: 10px; color: #666;">
            💡 Click lines/markers for details
        </div>
    </div>
    """

    m.get_root().html.add_child(folium.Element(legend_html))

    # Add JavaScript for select/deselect all buttons and URL state persistence
    # This needs to happen after the map and layers are created
    js_code = """
    <script>
    (function() {
        // Wait for map to be fully loaded
        window.addEventListener('load', function() {
            // Get all layer checkboxes
            function getLayerCheckboxes() {
                // Get the layer control container
                var layerControl = document.querySelector('.leaflet-control-layers-overlays');
                if (!layerControl) {
                    console.warn('Layer control not found');
                    return [];
                }

                // Get all input elements (checkboxes)
                var inputs = layerControl.querySelectorAll('input[type="checkbox"]');
                return Array.from(inputs);
            }

            // Get route checkboxes (exclude stops layer)
            function getRouteCheckboxes() {
                var allCheckboxes = getLayerCheckboxes();
                return allCheckboxes.filter(function(cb) {
                    var label = cb.parentElement.querySelector('span');
                    return label && label.textContent.includes('🚌 Route');
                });
            }

            // Save current layer states to URL
            function saveStateToURL() {
                var checkboxes = getLayerCheckboxes();
                var states = {};

                checkboxes.forEach(function(cb) {
                    var label = cb.parentElement.querySelector('span');
                    if (label) {
                        var layerName = label.textContent.trim();
                        states[layerName] = cb.checked;
                    }
                });

                // Encode states as URL parameter
                var stateParam = btoa(JSON.stringify(states));
                var url = new URL(window.location);
                url.searchParams.set('layers', stateParam);

                // Update URL without reloading page
                window.history.replaceState({}, '', url);
            }

            // Load layer states from URL
            function loadStateFromURL() {
                var url = new URL(window.location);
                var stateParam = url.searchParams.get('layers');

                if (!stateParam) return;

                try {
                    var states = JSON.parse(atob(stateParam));
                    var checkboxes = getLayerCheckboxes();

                    checkboxes.forEach(function(cb) {
                        var label = cb.parentElement.querySelector('span');
                        if (label) {
                            var layerName = label.textContent.trim();
                            if (layerName in states) {
                                // Trigger click only if state differs
                                if (cb.checked !== states[layerName]) {
                                    cb.click();
                                }
                            }
                        }
                    });
                } catch (e) {
                    console.error('Failed to load layer state from URL:', e);
                }
            }

            // Select all routes
            function selectAllRoutes() {
                var routeCheckboxes = getRouteCheckboxes();
                routeCheckboxes.forEach(function(cb) {
                    if (!cb.checked) {
                        cb.click();
                    }
                });
                saveStateToURL();
            }

            // Deselect all routes
            function deselectAllRoutes() {
                var routeCheckboxes = getRouteCheckboxes();
                routeCheckboxes.forEach(function(cb) {
                    if (cb.checked) {
                        cb.click();
                    }
                });
                saveStateToURL();
            }

            // Add event listeners to checkboxes to save state on change
            function attachCheckboxListeners() {
                var checkboxes = getLayerCheckboxes();
                checkboxes.forEach(function(cb) {
                    cb.addEventListener('change', function() {
                        saveStateToURL();
                    });
                });
            }

            // Attach button event listeners
            var selectAllBtn = document.getElementById('selectAllRoutes');
            var deselectAllBtn = document.getElementById('deselectAllRoutes');

            if (selectAllBtn) {
                selectAllBtn.addEventListener('click', selectAllRoutes);
            }

            if (deselectAllBtn) {
                deselectAllBtn.addEventListener('click', deselectAllRoutes);
            }

            // Wait a bit for Leaflet to fully initialize layers
            setTimeout(function() {
                attachCheckboxListeners();
                loadStateFromURL();
            }, 500);
        });
    })();
    </script>
    """

    m.get_root().html.add_child(folium.Element(js_code))

    return m


def main():
    print("=" * 70)
    print("BUS ROUTE VISUALIZATION TOOL (Enhanced with State Persistence)")
    print("=" * 70)

    # Read data
    print("\n[1/3] Reading data files...")

    try:
        stops = read_stops("./data/stops.csv")
        print(f"   ✓ Loaded {len(stops)} stops")
    except Exception as e:
        print(f"   ✗ Failed to load stops.csv: {e}")
        return

    try:
        routes = read_routes("./data/routes.csv")
        print(f"   ✓ Loaded {len(routes)} routes")
    except Exception as e:
        print(f"   ✗ Failed to load routes.csv: {e}")
        return

    try:
        route_sequences = read_route_stops("./data/route_stops.csv")
        print(f"   ✓ Loaded {len(route_sequences)} route sequences")
    except Exception as e:
        print(f"   ✗ Failed to load route_stops.csv: {e}")
        return

    # Check data consistency
    print("\n[2/3] Checking data consistency...")

    routes_without_sequence = [r for r in routes if r not in route_sequences]
    if routes_without_sequence:
        print(f"   ⚠  Routes without stop sequence: {routes_without_sequence}")

    sequences_without_route = [s for s in route_sequences if s not in routes]
    if sequences_without_route:
        print(f"   ⚠  Stop sequences without route info: {sequences_without_route}")

    active_routes = [r for r, info in routes.items() if info["is_active"]]
    print(f"   ✓ Active routes: {len(active_routes)}/{len(routes)}")

    # Create map
    print("\n[3/3] Creating map visualization...")
    print("-" * 70)

    m = create_map(stops, routes, route_sequences)

    # Save the map
    output_file = "data/visualizations/bus_routes_visualization.html"

    m.save(output_file)

    print("\n" + "=" * 70)
    print("✅ MAP GENERATION COMPLETE!")
    print("=" * 70)

    print(f"\n📁 Output file: {output_file}")
    print("\n✨ NEW FEATURES:")
    print("   • '✓ All' / '✗ None' buttons to toggle all routes at once")
    print("   • Routes sorted alphabetically (as strings)")
    print("   • Layer visibility state saved in URL")
    print("   • Share URL to preserve your layer selection")
    print("   • State persists across page refreshes")
    print("\n🔍 USAGE TIPS:")
    print("   1. Use '✓ All' button to show all routes")
    print("   2. Use '✗ None' button to hide all routes")
    print("   3. Toggle individual routes in layer control (top-right)")
    print("   4. Your selection is saved in the URL automatically")
    print("   5. Copy URL to share your current view with others")
    print("   6. Reload page - your layer selection will be restored")

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
