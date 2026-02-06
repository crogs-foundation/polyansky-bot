import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Sequence

import aiofiles
import aiofiles.os
import aiohttp
import contextily as ctx
import geopandas as gpd
import loguru
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point

from utils.get_path import create_path

logger = loguru.logger.bind(name=__name__)

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
    tile_provider: object = field(
        default_factory=lambda: ctx.providers.OpenStreetMap.Mapnik  # ty:ignore [unresolved-attribute]
    )
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

    # Concurrency
    max_concurrent_renders: int = 3


class RouteDrawer:
    def __init__(self, config: RenderConfig):
        self.config: RenderConfig = config
        self._session: aiohttp.ClientSession | None = None
        self._data_folder: Path = Path("./data/images")
        self._data: dict[MapIndex, bool] = {}
        self._init_lock = asyncio.Lock()

        # Rendering semaphore to limit concurrent matplotlib operations
        self._render_semaphore = asyncio.Semaphore(config.max_concurrent_renders)

        if self.config.cache_dir:
            cache_path = Path(self.config.cache_dir)
            cache_path.mkdir(parents=True, exist_ok=True)
            ctx.set_cache_dir(str(cache_path))
            logger.info(f"Tile cache initialized at: {cache_path.absolute()}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        await self._load_existing_maps()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self._session is None:
            async with self._init_lock:
                if self._session is None:
                    logger.debug("Initializing aiohttp session")
                    timeout = aiohttp.ClientTimeout(total=self.config.osrm_timeout_s)
                    connector = aiohttp.TCPConnector(
                        limit=10,  # Max total connections
                        limit_per_host=5,  # Max connections per host
                        ttl_dns_cache=300,  # DNS cache for 5 minutes
                    )
                    self._session = aiohttp.ClientSession(
                        timeout=timeout, connector=connector
                    )

    async def close(self):
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None
            logger.debug("Closed aiohttp session")

    async def _load_existing_maps(self):
        """Load existing maps asynchronously."""
        try:
            # Ensure directory exists
            self._data_folder.mkdir(parents=True, exist_ok=True)

            dir_content = await aiofiles.os.listdir(self._data_folder)
            data: dict[MapIndex, bool] = {}

            for file in dir_content:
                try:
                    name, postfix = file.split(".")
                    if postfix != "png":
                        continue
                    route_name, first_stop, last_stop = name.split("_", 2)
                    data[(route_name, first_stop, last_stop)] = True
                except ValueError:
                    continue

            self._data = data
            logger.info(f"Found {len(data)} cached maps")
        except FileNotFoundError:
            logger.warning(f"Data folder {self._data_folder} not found, creating it")
            self._data_folder.mkdir(parents=True, exist_ok=True)
            self._data = {}

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

    async def _osrm_route_geojson(
        self,
        stop_coords_latlon: Sequence[tuple[float, float]],
    ) -> list[LonLat]:
        """
        Fetch complete route geometry from OSRM in one request.
        Returns list of (lon, lat) coordinates following roads.
        """
        await self._ensure_session()

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
            headers = {"User-Agent": self.config.user_agent}
            if not self._session:
                raise RuntimeError("Couldn`t get session")
            async with self._session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()

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

        except asyncio.TimeoutError:
            logger.error(f"OSRM request timed out after {self.config.osrm_timeout_s}s")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"OSRM request failed: {e}")
            raise
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse OSRM response: {e}")
            raise

    @staticmethod
    @lru_cache(maxsize=128)
    def _create_gdf_route(route_lonlat_tuple: tuple[LonLat, ...]) -> gpd.GeoDataFrame:
        """
        Convert route coordinates to Web Mercator GeoDataFrame.
        Cached to avoid recomputing for identical routes.
        """
        gdf = gpd.GeoDataFrame(
            geometry=[LineString(route_lonlat_tuple)],
            crs="EPSG:4326",
        ).to_crs(epsg=3857)
        return gdf

    @staticmethod
    @lru_cache(maxsize=128)
    def _create_gdf_stops(stops_tuple: tuple[LatLonName, ...]) -> gpd.GeoDataFrame:
        """
        Convert stops to Web Mercator GeoDataFrame.
        Cached to avoid recomputing for identical stop sets.
        """
        gdf = gpd.GeoDataFrame(
            {
                "name": [s[2] for s in stops_tuple],
                "id": list(range(1, len(stops_tuple) + 1)),
            },
            geometry=[Point(s[1], s[0]) for s in stops_tuple],  # Point(lon, lat)
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

    async def _render_matplotlib(
        self,
        gdf_route: gpd.GeoDataFrame,
        gdf_stops: gpd.GeoDataFrame,
        stops: Sequence[LatLonName],
    ) -> bytes:
        """
        Render the matplotlib figure in executor (CPU-bound operation).
        Returns PNG bytes.
        """

        def _render():
            # Calculate figure size (square)
            figsize_inches = self.config.pixel_size / self.config.dpi

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
            logger.info(
                f"Downloading basemap tiles (zoom level: {self.config.basemap_zoom})"
            )
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

            # Save to bytes
            output = BytesIO()
            fig.tight_layout(pad=0.1)
            fig.savefig(
                output,
                dpi=self.config.dpi,
                bbox_inches="tight",
                pad_inches=0,
                facecolor="white",
                # Optimize PNG compression
                pil_kwargs={"optimize": True},
            )
            plt.close(fig)

            return output.getvalue()

        async with self._render_semaphore:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _render)

    async def render_route_map_png(
        self,
        route_name: str,
        stops: Sequence[LatLonName],
        *,
        use_osrm: bool = True,
    ) -> bytes:
        """
        Render a high-quality square route map with OSM tiles.

        Args:
            route_name: Name of the route
            stops: List of (lat, lon, name) tuples for each stop
            use_osrm: Whether to use OSRM routing (True) or straight lines (False)

        Returns:
            PNG image data as bytes
        """
        logger.info("Starting route map rendering")
        logger.debug(f"{stops=}")
        self._validate_stops(stops)

        # Check cache
        map_index = (route_name, stops[0][2], stops[-1][2])
        if self._data.get(map_index):
            logger.info("Map found in cache. Reading...")
            file_path = create_path(
                f"{self._data_folder}/{map_index[0]}_{map_index[1]}_{map_index[2]}.png"
            )
            async with aiofiles.open(file_path, "rb") as f:
                return await f.read()

        # Prepare coordinates
        stop_coords_latlon = [(lat, lon) for lat, lon, _ in stops]

        # Fetch route geometry
        if use_osrm:
            try:
                route_lonlat = await self._osrm_route_geojson(stop_coords_latlon)
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
        gdf_route: gpd.GeoDataFrame = self._create_gdf_route(tuple(route_lonlat))
        gdf_stops: gpd.GeoDataFrame = self._create_gdf_stops(tuple(stops))

        logger.info(
            f"Creating {self.config.pixel_size}x{self.config.pixel_size}px image at {self.config.dpi} DPI"
        )

        # Render matplotlib figure (CPU-bound, run in executor)
        data = await self._render_matplotlib(gdf_route, gdf_stops, stops)

        # Save to file asynchronously
        file_path = create_path(
            f"{self._data_folder}/{map_index[0]}_{map_index[1]}_{map_index[2]}.png"
        )
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data)

        self._data[map_index] = True
        logger.info("File is written")

        return data
