"""
cost_map.py
===========

Backend module for the Faustini rover planner. Reads config.json, streams
the relevant DEM window via GDAL /vsicurl, and builds a slope-based
traversability cost map. No plotting or interactivity lives here — this
module only produces arrays/numbers for path_planner.py to consume.

Requires: rasterio, pyproj, numpy
    pip install rasterio pyproj numpy
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window

RC = Tuple[int, int]


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #

def load_config(config_path: Path | str = "config.json") -> Dict[str, Any]:
    """Load mission parameters (coordinates, DEM source, slope limit) from JSON.

    Args:
        config_path: Path to config.json.

    Returns:
        Dict with keys: dem_url, start {lat, lon, label}, goal {lat, lon,
        label}, radius_m, max_slope_deg, output_png.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if required keys are missing.
    """
    config_path = Path(config_path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r") as f:
        config = json.load(f)

    required_keys = {"dem_url", "start", "goal", "radius_m", "max_slope_deg", "output_png"}
    missing = required_keys - config.keys()
    if missing:
        raise ValueError(f"config.json missing required keys: {sorted(missing)}")
    for point_name in ("start", "goal"):
        missing_coords = {"lat", "lon"} - config[point_name].keys()
        if missing_coords:
            raise ValueError(f"config.json '{point_name}' missing keys: {sorted(missing_coords)}")

    return config


# --------------------------------------------------------------------------- #
# Coordinate transforms
# --------------------------------------------------------------------------- #

def latlon_to_projected(lat: float, lon: float, stereo_crs: CRS) -> Tuple[float, float]:
    """Convert Moon-fixed lat/lon (degrees) to the raster's projected x, y (metres)."""
    radius_m = stereo_crs.ellipsoid.semi_major_metre
    geographic_crs = CRS.from_proj4(f"+proj=longlat +R={radius_m} +no_defs")
    transformer = Transformer.from_crs(geographic_crs, stereo_crs, always_xy=True)
    return transformer.transform(lon, lat)


def latlon_to_pixel(lat: float, lon: float, meta: Dict[str, Any]) -> RC:
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
            f"{meta['shape']} crop. Increase 'radius_m' in config.json, or "
            f"move the point closer to the goal."
        )
    return row, col


# --------------------------------------------------------------------------- #
# DEM download / clip
# --------------------------------------------------------------------------- #

def clip_dem(url: str, center_lat: float, center_lon: float, radius_m: float) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Stream-clip a square DEM window centred on (center_lat, center_lon) via /vsicurl.

    Args:
        url: GDAL /vsicurl path to the remote GeoTIFF.
        center_lat: Centre latitude, degrees.
        center_lon: Centre longitude, degrees.
        radius_m: Half-width of the clipped square, metres.

    Returns:
        Tuple of (elevation array float32, meta dict with pixel_size_m,
        origin_x_m, origin_y_m, shape, projection_wkt).
    """
    with rasterio.open(url) as src:
        stereo_crs = CRS.from_wkt(src.crs.to_wkt())
        pixel_size_m = abs(src.transform.a)  # assumes square pixels

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




# --------------------------------------------------------------------------- #
# Slope-based cost map
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
        best, best_dist = None, math.inf
        r_lo, r_hi = max(r0 - radius, 0), min(r0 + radius, n_rows - 1)
        c_lo, c_hi = max(c0 - radius, 0), min(c0 + radius, n_cols - 1)
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
        f"Try raising 'max_slope_deg' in config.json."
    )


# --------------------------------------------------------------------------- #
# Top-level convenience function — this is what path_planner.py calls
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Top-level convenience function
# --------------------------------------------------------------------------- #

def get_cost_map(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full backend pipeline: clip DEM around a center point,
    compute slope, and build cost map.
    """
    # 1. Clip around the specific center defined in config
    # Ensure your config.json has a "center" object: {"lat": -87.23, "lon": 85.22}
    center = config.get("center", config["goal"])  # Fallback to goal if center missing

    elevation, meta = clip_dem(
        config["dem_url"],
        center["lat"],
        center["lon"],
        config["radius_m"],
    )

    # 2. Convert start/goal to pixel coordinates
    start_rc = latlon_to_pixel(config["start"]["lat"], config["start"]["lon"], meta)
    goal_rc = latlon_to_pixel(config["goal"]["lat"], config["goal"]["lon"], meta)

    # 3. Compute cost map
    slope_deg = slope_from_dem(elevation, meta["pixel_size_m"])
    cost_map = build_cost_map(slope_deg, config["max_slope_deg"])

    # 4. Snap to nearest passable
    snapped_start = nearest_passable_cell(cost_map, start_rc)
    snapped_goal = nearest_passable_cell(cost_map, goal_rc)

    return {
        "elevation": elevation,
        "cost_map": cost_map,
        "slope_deg": slope_deg,
        "meta": meta,
        "start_rc": snapped_start,
        "goal_rc": snapped_goal,
    }