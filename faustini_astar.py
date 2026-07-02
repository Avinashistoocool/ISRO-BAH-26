"""
faustini_astar.py
==================
Minimal A* rover-path planner: rim -> floor of Faustini crater.

Streams a DEM crop from the LOLA 80S mosaic via GDAL /vsicurl (no full
mosaic download), derives a slope-based cost map, runs 8-connected A*,
and ALWAYS saves a PNG of the result (uses the non-interactive "Agg"
backend, so it never depends on a display or a show=True call).

Requires: rasterio, pyproj, numpy, matplotlib
    pip install rasterio pyproj numpy matplotlib
"""

from __future__ import annotations

import heapq
import itertools
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive: savefig always works, no display needed
import matplotlib.pyplot as plt
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window

# ============================================================================
# EDIT THESE — start (rim) and goal (floor) coordinates, in degrees.
# Faustini crater is centred around roughly lat -87.85, lon 77-82 (its exact
# rim/floor coordinates depend on which point you want; adjust freely).
# ============================================================================
START_LAT = -87.68     # rim of Faustini crater
START_LON = 77.30

GOAL_LAT = -87.24280      # floor / target point inside Faustini crater
GOAL_LON = 87.91984

RADIUS_M = 30000.0      # half-width (m) of the DEM crop — must contain both points
MAX_SLOPE_DEG = 15.0    # cells steeper than this are treated as impassable
OUTPUT_PNG = Path("outputs/faustini_path.png")

DEM_URL = "/vsicurl/https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF"
# ============================================================================

RC = Tuple[int, int]
SQRT2 = math.sqrt(2.0)
_NEIGHBOURS: Tuple[Tuple[int, int, float], ...] = (
    (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
    (-1, -1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (1, 1, SQRT2),
)


# --------------------------------------------------------------------------- #
# DEM download / coordinate transforms
# --------------------------------------------------------------------------- #

def latlon_to_projected(lat: float, lon: float, stereo_crs: CRS) -> Tuple[float, float]:
    """Convert Moon-fixed lat/lon (degrees) to the raster's projected x, y (metres)."""
    radius_m = stereo_crs.ellipsoid.semi_major_metre
    geographic_crs = CRS.from_proj4(f"+proj=longlat +R={radius_m} +no_defs")
    transformer = Transformer.from_crs(geographic_crs, stereo_crs, always_xy=True)
    return transformer.transform(lon, lat)


def clip_dem(url: str, center_lat: float, center_lon: float, radius_m: float) -> Tuple[np.ndarray, Dict]:
    """Stream-clip a square DEM window centred on (center_lat, center_lon)."""
    with rasterio.open(url) as src:
        stereo_crs = CRS.from_wkt(src.crs.to_wkt())
        pixel_size_m = abs(src.transform.a)

        x_m, y_m = latlon_to_projected(center_lat, center_lon, stereo_crs)
        inv_transform = ~src.transform
        center_col, center_row = inv_transform * (x_m, y_m)
        center_row, center_col = int(round(center_row)), int(round(center_col))

        half_px = int(round(radius_m / pixel_size_m))
        row_off, col_off = max(center_row - half_px, 0), max(center_col - half_px, 0)
        row_stop = min(center_row + half_px, src.height)
        col_stop = min(center_col + half_px, src.width)

        window = Window(col_off, row_off, col_stop - col_off, row_stop - row_off)
        elevation = src.read(1, window=window).astype(np.float32)
        crop_transform = src.window_transform(window)

    meta = {
        "pixel_size_m": pixel_size_m,
        "origin_x_m": crop_transform.c,
        "origin_y_m": crop_transform.f,
        "shape": elevation.shape,
        "projection_wkt": stereo_crs.to_wkt(),
    }
    return elevation, meta


def latlon_to_pixel(lat: float, lon: float, meta: Dict) -> RC:
    """Convert a lat/lon to (row, col) inside the crop described by `meta`."""
    stereo_crs = CRS.from_wkt(meta["projection_wkt"])
    x_m, y_m = latlon_to_projected(lat, lon, stereo_crs)
    col = (x_m - meta["origin_x_m"]) / meta["pixel_size_m"]
    row = (meta["origin_y_m"] - y_m) / meta["pixel_size_m"]
    row, col = int(round(row)), int(round(col))

    n_rows, n_cols = meta["shape"]
    if not (0 <= row < n_rows and 0 <= col < n_cols):
        raise ValueError(
            f"({lat}, {lon}) -> pixel ({row}, {col}) falls outside the "
            f"{meta['shape']} crop. Increase RADIUS_M or move the point closer "
            f"to ({GOAL_LAT}, {GOAL_LON})."
        )
    return row, col


# --------------------------------------------------------------------------- #
# Simplified cost map (slope only)
# --------------------------------------------------------------------------- #

def slope_from_dem(elevation: np.ndarray, pixel_size_m: float) -> np.ndarray:
    """Local slope in degrees, from the elevation raster's gradient."""
    gy, gx = np.gradient(elevation, pixel_size_m)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


def build_cost_map(slope_deg: np.ndarray, max_slope_deg: float) -> np.ndarray:
    """Cost = normalised slope in [0, 1]; cells steeper than max_slope_deg are inf."""
    cost = np.clip(slope_deg / max_slope_deg, 0.0, 1.0).astype(np.float32)
    cost = np.where(slope_deg > max_slope_deg, np.inf, cost).astype(np.float32)
    return cost


# --------------------------------------------------------------------------- #
# Nearest-passable-cell snapping
# --------------------------------------------------------------------------- #

def nearest_passable_cell(cost_map: np.ndarray, rc: RC, max_search_radius_px: int = 200) -> RC:
    """Return the closest finite-cost cell to `rc` (expanding ring search).

    Useful because a lat/lon you pick (e.g. dead-center of a crater floor)
    can land exactly on a pixel that's too steep to be traversable, even
    though passable ground is right next to it. Returns `rc` unchanged if
    it's already passable.

    Args:
        cost_map: 2D cost array (inf = impassable).
        rc: (row, col) point to snap.
        max_search_radius_px: How far out (in pixels) to search before
            giving up.

    Returns:
        (row, col) of the nearest passable cell.

    Raises:
        ValueError: if no passable cell is found within max_search_radius_px.
    """
    r0, c0 = rc
    n_rows, n_cols = cost_map.shape
    if 0 <= r0 < n_rows and 0 <= c0 < n_cols and np.isfinite(cost_map[r0, c0]):
        return rc

    for radius in range(1, max_search_radius_px + 1):
        best = None
        best_dist = math.inf
        r_lo, r_hi = max(r0 - radius, 0), min(r0 + radius, n_rows - 1)
        c_lo, c_hi = max(c0 - radius, 0), min(c0 + radius, n_cols - 1)
        # Only check the ring at this radius (cells checked at smaller radii
        # already failed), scanning the bounding box border.
        ring_cells = (
            [(r_lo, c) for c in range(c_lo, c_hi + 1)] +
            [(r_hi, c) for c in range(c_lo, c_hi + 1)] +
            [(r, c_lo) for r in range(r_lo, r_hi + 1)] +
            [(r, c_hi) for r in range(r_lo, r_hi + 1)]
        )
        for r, c in ring_cells:
            if np.isfinite(cost_map[r, c]):
                d = math.hypot(r - r0, c - c0)
                if d < best_dist:
                    best_dist, best = d, (r, c)
        if best is not None:
            return best

    raise ValueError(
        f"No passable cell found within {max_search_radius_px}px of {rc}. "
        f"Try raising MAX_SLOPE_DEG."
    )


# --------------------------------------------------------------------------- #
# A*
# --------------------------------------------------------------------------- #

def _octile(a: RC, b: RC, min_cost: float) -> float:
    dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
    dd = min(dr, dc)
    return min_cost * (dr + dc - 2 * dd + SQRT2 * dd)


def a_star(cost_map: np.ndarray, start: RC, goal: RC) -> Optional[List[RC]]:
    n_rows, n_cols = cost_map.shape
    for name, rc in (("start", start), ("goal", goal)):
        r, c = rc
        if not (0 <= r < n_rows and 0 <= c < n_cols):
            raise ValueError(f"{name}={rc} out of bounds for {cost_map.shape}")
        if not np.isfinite(cost_map[r, c]):
            raise ValueError(f"{name}={rc} is on an impassable cell")

    finite = cost_map[np.isfinite(cost_map)]
    min_cost = max(float(np.min(finite[finite > 0])) if np.any(finite > 0) else 1e-6, 1e-9)

    counter = itertools.count()
    open_heap: List[Tuple[float, int, RC]] = [(_octile(start, goal, min_cost), next(counter), start)]
    g_score: Dict[RC, float] = {start: 0.0}
    came_from: Dict[RC, RC] = {}
    closed: set = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1]
        closed.add(current)

        cr, cc = current
        for dr, dc, mult in _NEIGHBOURS:
            nr, nc = cr + dr, cc + dc
            if not (0 <= nr < n_rows and 0 <= nc < n_cols):
                continue
            ncost = cost_map[nr, nc]
            if not np.isfinite(ncost):
                continue
            neighbour = (nr, nc)
            if neighbour in closed:
                continue
            tentative_g = g_score[current] + ncost * mult
            if tentative_g < g_score.get(neighbour, math.inf):
                g_score[neighbour] = tentative_g
                came_from[neighbour] = current
                f = tentative_g + _octile(neighbour, goal, min_cost)
                heapq.heappush(open_heap, (f, next(counter), neighbour))

    return None


# --------------------------------------------------------------------------- #
# Visualisation — always saved, never depends on a display
# --------------------------------------------------------------------------- #

def plot_path(
    elevation: np.ndarray,
    cost_map: np.ndarray,
    path: List[RC],
    start: RC,
    goal: RC,
    out_path: Path,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 8), dpi=150)
    ax.imshow(elevation, cmap="gray")
    ax.imshow(np.ma.masked_invalid(cost_map), cmap="plasma", alpha=0.4)

    if path:
        arr = np.array(path)
        ax.plot(arr[:, 1], arr[:, 0], color="cyan", linewidth=2.5, label="A* path")

    ax.scatter([start[1]], [start[0]], marker="*", s=220, color="lime",
               edgecolor="black", linewidth=1.0, zorder=10, label="Start (rim)")
    ax.scatter([goal[1]], [goal[0]], marker="D", s=110, color="red",
               edgecolor="black", linewidth=1.0, zorder=10, label="Goal (crater)")

    ax.legend(loc="lower right", framealpha=0.85)
    ax.set_title("Faustini Crater — A* Path (Rim \u2192 Floor)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Column (pixel)")
    ax.set_ylabel("Row (pixel)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    print(f"Clipping DEM around ({GOAL_LAT}, {GOAL_LON}), radius {RADIUS_M / 1000:.0f} km...")
    elevation, meta = clip_dem(DEM_URL, GOAL_LAT, GOAL_LON, RADIUS_M)

    start_rc = latlon_to_pixel(START_LAT, START_LON, meta)
    goal_rc = latlon_to_pixel(GOAL_LAT, GOAL_LON, meta)
    print(f"start_rc={start_rc}  goal_rc={goal_rc}  crop shape={meta['shape']}")

    slope_deg = slope_from_dem(elevation, meta["pixel_size_m"])
    cost_map = build_cost_map(slope_deg, MAX_SLOPE_DEG)

    snapped_start = nearest_passable_cell(cost_map, start_rc)
    snapped_goal = nearest_passable_cell(cost_map, goal_rc)
    if snapped_start != start_rc:
        print(f"Start {start_rc} was impassable (slope > {MAX_SLOPE_DEG}\u00b0); snapped to {snapped_start}.")
    if snapped_goal != goal_rc:
        print(f"Goal {goal_rc} was impassable (slope > {MAX_SLOPE_DEG}\u00b0); snapped to {snapped_goal}.")
    start_rc, goal_rc = snapped_start, snapped_goal

    path = a_star(cost_map, start_rc, goal_rc)
    if path is None:
        print("No path found. Try raising MAX_SLOPE_DEG or increasing RADIUS_M.")
        path = []
    else:
        length_px = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path[:-1], path[1:]))
        length_km = length_px * meta["pixel_size_m"] / 1000.0
        print(f"Path found: {len(path)} waypoints, {length_km:.2f} km")

    out_path = plot_path(elevation, cost_map, path, start_rc, goal_rc, OUTPUT_PNG)
    print(f"Saved image: {out_path.resolve()}")


if __name__ == "__main__":
    main()