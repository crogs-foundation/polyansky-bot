from dataclasses import dataclass, field
from io import BytesIO
from os import listdir
from pathlib import Path
from typing import Sequence

import contextily as ctx
import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import requests
from loguru import logger
from requests.adapters import HTTPAdapter, Retry
from shapely.geometry import LineString, Point

MapIndex = tuple[str, str, str]  # (route_name, first_stop, last_stop)
LatLonName = tuple[float, float, str]  # (lat, lon, name)
LonLat = tuple[float, float]  # (lon, lat)


@dataclass(frozen=True)
class RenderConfig:
    """Configuration for map rendering with high-quality output."""

    # Output sizing: SQUARE format with high DPI for crisp text
    pixel_size: int = 1600  # Square output (1600x1600)
    dpi: int = 350  # High DPI for sharp text/labels

    # Basemap
    tile_provider: object = field(default_factory=ctx.providers.OpenStreetMap.Mapnik)  # ty: ignore[unresolved-attribute]
    basemap_zoom: int | str = 16  # Fixed zoom for consistent quality
    cache_dir: str | None = ".ctx_tile_cache"

    # Layout / bounds
    buffer_ratio: float = 0.25  # Padding around route

    # Route styling
    route_color: str = "#1565C0"  # Deep blue
    route_width: float = 1
    route_halo_color: str = "white"
    route_halo_width: float = 1
    route_alpha: float = 0.95

    # Marker colors
    start_color: str = "#1B5E20"  # Dark green
    mid_color: str = "#F57F17"  # Amber/orange
    end_color: str = "#B71C1C"  # Dark red

    # Marker sizes (scaled for square format)
    marker_size_start_end: int = 20
    marker_size_mid: int = 11
    marker_edge_color: str = "white"
    marker_edge_width: float = 0.3

    # Font sizes (larger for high DPI)
    number_fontsize: int = 2
    label_fontsize: int = 2
    ends_ratio: float = 1.3

    # OSRM
    osrm_base_url: str = "http://router.project-osrm.org/route/v1/driving"
    osrm_timeout_s: float = 10.0
    user_agent: str = "route-map-renderer/2.0"


class RouteDrawer:
    def __init__(self, config: RenderConfig):
        self.config: RenderConfig = config
        self.session: requests.Session = self._make_session()
        self._data_folder: Path = Path("./data/images")
        self._data: dict[MapIndex, bool] = self._get_already_created(self._data_folder)

        if self.config.cache_dir:
            cache_path = Path(self.config.cache_dir)
            cache_path.mkdir(parents=True, exist_ok=True)
            ctx.set_cache_dir(str(cache_path))
            logger.info(f"Tile cache initialized at: {cache_path.absolute()}")

    def _make_session(self) -> requests.Session:
        """Create requests session with retry logic."""
        logger.debug("Initializing HTTP session with retry logic")
        s = requests.Session()
        retries = Retry(
            total=4,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        s.mount("http://", HTTPAdapter(max_retries=retries))
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _get_already_created(self, dir: Path) -> dict[MapIndex, bool]:
        dir_content = listdir(dir)
        data: dict[MapIndex, bool] = {}
        for file in dir_content:
            try:
                name, postfix = file.split(".")
                route_name, first_stop, last_stop = name.split("_")
                data[(route_name, first_stop, last_stop)] = True
            except ValueError:
                continue
        logger.info(f"Found {len(data.keys())} maps")
        return data

    def _validate_stops(self, stops: Sequence[LatLonName]) -> None:
        """Validate stop coordinates."""
        logger.info(f"Validating {len(stops)} stops")

        if len(stops) < 2:
            raise ValueError("Need at least 2 stops")

        for i, (lat, lon, name) in enumerate(stops):
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(
                    f"Invalid coordinates for stop {i + 1} '{name}': ({lat}, {lon})"
                )
            logger.debug(f"  Stop {i + 1}: {name} at ({lat:.6f}, {lon:.6f})")

    def _osrm_route_geojson(
        self,
        stop_coords_latlon: Sequence[tuple[float, float]],
    ) -> list[LonLat]:
        """
        Fetch complete route geometry from OSRM in one request.
        Returns list of (lon, lat) coordinates following roads.
        """
        logger.info(
            f"Requesting route geometry for {len(stop_coords_latlon)} waypoints from OSRM"
        )

        if len(stop_coords_latlon) < 2:
            logger.warning("Less than 2 coordinates provided")
            return []

        # Build OSRM request URL
        coord_str = ";".join(f"{lon},{lat}" for (lat, lon) in stop_coords_latlon)
        url = f"{self.config.osrm_base_url}/{coord_str}?overview=full&geometries=geojson"

        logger.debug(f"OSRM URL: {url[:100]}...")

        try:
            resp = self.session.get(
                url,
                headers={"User-Agent": self.config.user_agent},
                timeout=self.config.osrm_timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != "Ok":
                raise RuntimeError(f"OSRM returned code: {data.get('code')}")

            if not data.get("routes"):
                raise RuntimeError("No routes in OSRM response")

            coords = data["routes"][0]["geometry"]["coordinates"]
            route_points = [(float(lon), float(lat)) for lon, lat in coords]

            distance_km = data["routes"][0].get("distance", 0) / 1000
            duration_min = data["routes"][0].get("duration", 0) / 60

            logger.info(
                f"✓ Route received: {len(route_points)} points, {distance_km:.2f} km, ~{duration_min:.0f} min"
            )
            return route_points

        except requests.exceptions.Timeout:
            logger.error(f"OSRM request timed out after {self.config.osrm_timeout_s}s")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"OSRM request failed: {e}")
            raise
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse OSRM response: {e}")
            raise

    def _to_web_mercator_route(self, route_lonlat: Sequence[LonLat]) -> gpd.GeoDataFrame:
        """Convert route coordinates to Web Mercator GeoDataFrame."""
        logger.debug(f"Converting {len(route_lonlat)} route points to Web Mercator")
        gdf = gpd.GeoDataFrame(
            geometry=[LineString(route_lonlat)],
            crs="EPSG:4326",
        ).to_crs(epsg=3857)
        return gdf

    def _to_web_mercator_stops(self, stops: Sequence[LatLonName]) -> gpd.GeoDataFrame:
        """Convert stops to Web Mercator GeoDataFrame."""
        logger.debug(f"Converting {len(stops)} stops to Web Mercator")
        gdf = gpd.GeoDataFrame(
            {"name": [s[2] for s in stops], "id": list(range(1, len(stops) + 1))},
            geometry=[Point(s[1], s[0]) for s in stops],  # Point(lon, lat)
            crs="EPSG:4326",
        ).to_crs(epsg=3857)
        return gdf

    def _set_bounds(
        self, ax: plt.Axes, gdf_route_3857: gpd.GeoDataFrame, buffer_ratio: float
    ) -> None:
        """Calculate and set axis bounds with buffer."""
        minx, miny, maxx, maxy = gdf_route_3857.total_bounds
        dx = max(maxx - minx, 1.0)
        dy = max(maxy - miny, 1.0)

        buffer_x = dx * buffer_ratio
        buffer_y = dy * buffer_ratio

        ax.set_xlim(minx - buffer_x, maxx + buffer_x)
        ax.set_ylim(miny - buffer_y, maxy + buffer_y)

        logger.debug(
            f"Map bounds: X=[{minx:.0f}, {maxx:.0f}], Y=[{miny:.0f}, {maxy:.0f}] (buffer: {buffer_ratio * 100}%)"
        )

    def render_route_map_png(
        self,
        route_name: str,
        stops: Sequence[LatLonName],
        *,
        use_osrm: bool = True,
    ) -> bytes:
        """
        Render a high-quality square route map with OSM tiles.

        Args:
            stops: List of (lat, lon, name) tuples for each stop
            use_osrm: Whether to use OSRM routing (True) or straight lines (False)

        Returns:
            Path to the generated PNG file
        """
        logger.info("Starting route map rendering")

        self._validate_stops(stops)

        map_index = (route_name, stops[0][2], stops[-1][2])
        if self._data.get(map_index):
            with open(
                f"{self._data_folder}/{map_index[0]}_{map_index[1]}_{map_index[2]}.png",
                "rb",
            ) as f:
                return f.read()

        output = BytesIO()

        # Setup tile caching
        if self.config.cache_dir:
            cache_path = Path(self.config.cache_dir)
            cache_path.mkdir(parents=True, exist_ok=True)
            ctx.set_cache_dir(str(cache_path))
            logger.info(f"Tile cache directory: {cache_path.absolute()}")

        # Create HTTP session
        stop_coords_latlon = [(lat, lon) for lat, lon, _ in stops]

        # Fetch route geometry
        if use_osrm:
            try:
                route_lonlat = self._osrm_route_geojson(stop_coords_latlon)
            except Exception as e:
                logger.warning(
                    f"OSRM routing failed: {e}. Falling back to straight lines."
                )
                route_lonlat = [(lon, lat) for (lat, lon) in stop_coords_latlon]
        else:
            logger.info("Using straight-line routing (OSRM disabled)")
            route_lonlat = [(lon, lat) for (lat, lon) in stop_coords_latlon]

        # Convert to GeoDataFrames
        logger.info("Preparing geographic data")
        gdf_route = self._to_web_mercator_route(route_lonlat)
        gdf_stops = self._to_web_mercator_stops(stops)

        # Calculate figure size (square)
        figsize_inches = self.config.pixel_size / self.config.dpi
        logger.info(
            f"Creating {self.config.pixel_size}x{self.config.pixel_size}px image at {self.config.dpi} DPI"
        )
        logger.debug(f"Figure size: {figsize_inches:.2f}x{figsize_inches:.2f} inches")

        # Configure matplotlib for high quality text
        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "font.weight": "normal",
                "axes.unicode_minus": False,
            }
        )

        # Create figure
        fig, ax = plt.subplots(
            figsize=(figsize_inches, figsize_inches), dpi=self.config.dpi
        )

        # Set bounds first (needed for contextily)
        self._set_bounds(ax, gdf_route, self.config.buffer_ratio)

        # Download and add basemap tiles
        logger.info(f"Downloading basemap tiles (zoom level: {self.config.basemap_zoom})")
        try:
            ctx.add_basemap(
                ax,
                source=self.config.tile_provider,
                zoom=self.config.basemap_zoom,
                attribution_size=6,
                reset_extent=False,
            )
            logger.info("✓ Basemap tiles loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load basemap: {e}")
            raise

        # Draw route with halo effect
        logger.info("Drawing route line")
        gdf_route.plot(
            ax=ax,
            color=self.config.route_halo_color,
            linewidth=self.config.route_halo_width,
            alpha=0.85,
            capstyle="round",
            joinstyle="round",
            zorder=3,
        )
        gdf_route.plot(
            ax=ax,
            color=self.config.route_color,
            linewidth=self.config.route_width,
            alpha=self.config.route_alpha,
            capstyle="round",
            joinstyle="round",
            zorder=4,
        )

        # Prepare marker colors and sizes
        n = len(stops)
        colors = (
            [self.config.start_color]
            + [self.config.mid_color] * (n - 2)
            + [self.config.end_color]
        )
        sizes = (
            [self.config.marker_size_start_end]
            + [self.config.marker_size_mid] * (n - 2)
            + [self.config.marker_size_start_end]
        )

        # Draw markers
        logger.info(f"Drawing {n} stop markers")
        xs = gdf_stops.geometry.x.to_numpy()
        ys = gdf_stops.geometry.y.to_numpy()

        ax.scatter(
            xs,
            ys,
            s=sizes,
            c=colors,
            edgecolors=self.config.marker_edge_color,
            linewidths=self.config.marker_edge_width,
            zorder=5,
        )

        # Add labels
        logger.info("Adding stop labels and numbers")
        idx_end = len(gdf_stops) - 1
        for i, row in gdf_stops.iterrows():
            ratio = 1
            if i == 0 or i == idx_end:
                ratio = self.config.ends_ratio
            # Number inside marker
            ax.annotate(
                str(int(row["id"])),
                (row.geometry.x, row.geometry.y),
                ha="center",
                va="center",
                fontsize=self.config.number_fontsize * ratio,
                fontweight="bold",
                color="white",
                zorder=6,
            )

            # Stop name with white outline
            t = ax.annotate(
                row["name"],
                (row.geometry.x, row.geometry.y),
                xytext=(2, 2),
                # xytext=(10, 10),
                textcoords="offset points",
                fontsize=self.config.label_fontsize * ratio,
                fontweight="bold",
                color="#1F2937",
                zorder=7,
            )
            t.set_path_effects(
                [
                    pe.withStroke(
                        linewidth=self.config.label_fontsize / 3, foreground="white"
                    )
                ]
            )

        ax.set_axis_off()

        # Save
        logger.info("Write map to bytes")
        fig.tight_layout(pad=0.1)
        fig.savefig(
            output,
            dpi=self.config.dpi,
            bbox_inches="tight",
            pad_inches=0,
            facecolor="white",
        )
        plt.close(fig)

        data = output.getvalue()

        with open(
            f"{self._data_folder}/{map_index[0]}_{map_index[1]}_{map_index[2]}.png", "wb"
        ) as f:
            f.write(data)

        logger.info("File is written")

        return data
