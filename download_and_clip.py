"""
download_and_clip.py
=====================

Streams a square window of the LOLA 80S 20mpp south-pole DEM mosaic around
a given lat/lon (via GDAL /vsicurl — no full-mosaic download), saves the
elevation crop as a .npy, and saves a companion metadata JSON with
everything needed to convert between pixel (row, col) and Moon-fixed
lat/lon *within that crop* — which is exactly what you need to define
start_rc / goal_rc for path_planner.a_star().

Requires: rasterio, pyproj, numpy
    pip install rasterio pyproj numpy

Note: GDAL must be built with curl support for /vsicurl to work (this is
the default on most rasterio wheel installs from PyPI/conda-forge).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window

# =========================
# CONFIG
# =========================
URL = "/vsicurl/https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF"
LAT = -87.85
LON = 82.0
RADIUS_M = 30000  # half-width of the clipped square, in metres
OUTPUT = "lunar_south_pole_full.npy"
META_OUTPUT = "lunar_south_pole_full_meta.json"


# --------------------------------------------------------------------------- #
# Coordinate transforms
# --------------------------------------------------------------------------- #

def _build_geographic_to_stereo_transformer(stereo_crs: CRS) -> Transformer:
    """Build a lat/lon -> stereographic-x/y transformer matching the raster's own CRS.

    Reads the sphere radius directly from the raster's embedded CRS ellipsoid
    rather than hardcoding it, so this stays correct even if a different
    LOLA product (different radius/frame) is swapped in later.

    Args:
        stereo_crs: A pyproj.CRS instance (not rasterio.crs.CRS — callers
            reading a raster's CRS via rasterio must convert it first with
            `pyproj.CRS.from_wkt(src.crs.to_wkt())`).
    """
    if not isinstance(stereo_crs, CRS):
        stereo_crs = CRS.from_wkt(stereo_crs.to_wkt())
    radius_m = stereo_crs.ellipsoid.semi_major_metre
    geographic_crs = CRS.from_proj4(f"+proj=longlat +R={radius_m} +no_defs")
    return Transformer.from_crs(geographic_crs, stereo_crs, always_xy=True)


def latlon_to_projected(lat: float, lon: float, stereo_crs: CRS) -> Tuple[float, float]:
    """Convert Moon-fixed lat/lon (degrees) to the raster's projected x, y (metres)."""
    transformer = _build_geographic_to_stereo_transformer(stereo_crs)
    x_m, y_m = transformer.transform(lon, lat)
    return x_m, y_m


def latlon_to_pixel_in_crop(lat: float, lon: float, meta: dict) -> Tuple[int, int]:
    """Convert a lat/lon to (row, col) inside a crop described by `meta`.

    Use this to build start_rc / goal_rc for path_planner.a_star() from any
    lat/lon you pick (e.g. a candidate landing site on the PSR rim, or the
    doubly-shadowed floor of Faustini crater), as long as the point falls
    inside the region you clipped.

    Args:
        lat: Latitude, degrees.
        lon: Longitude, degrees.
        meta: The metadata dict saved alongside the crop (origin_x_m,
            origin_y_m, pixel_size_m, projection_wkt, shape).

    Returns:
        (row, col) tuple. Caller should verify this falls within meta['shape']
        and lands on a passable cell in cost_map before using it as start/goal.
    """
    stereo_crs = CRS.from_wkt(meta["projection_wkt"])
    x_m, y_m = latlon_to_projected(lat, lon, stereo_crs)
    col = (x_m - meta["origin_x_m"]) / meta["pixel_size_m"]
    row = (meta["origin_y_m"] - y_m) / meta["pixel_size_m"]
    row, col = int(round(row)), int(round(col))

    n_rows, n_cols = meta["shape"]
    if not (0 <= row < n_rows and 0 <= col < n_cols):
        raise ValueError(
            f"lat={lat}, lon={lon} maps to pixel (row={row}, col={col}), "
            f"which falls outside the clipped crop of shape {meta['shape']}. "
            f"Pick a point closer to the crop centre, or re-clip with a larger RADIUS_M."
        )
    return row, col


def pixel_to_latlon_in_crop(row: int, col: int, meta: dict) -> Tuple[float, float]:
    """Inverse of latlon_to_pixel_in_crop — useful for sanity-checking a path."""
    stereo_crs = CRS.from_wkt(meta["projection_wkt"])
    radius_m = stereo_crs.ellipsoid.semi_major_metre
    geographic_crs = CRS.from_proj4(f"+proj=longlat +R={radius_m} +no_defs")
    transformer = Transformer.from_crs(stereo_crs, geographic_crs, always_xy=True)

    x_m = meta["origin_x_m"] + col * meta["pixel_size_m"]
    y_m = meta["origin_y_m"] - row * meta["pixel_size_m"]
    lon, lat = transformer.transform(x_m, y_m)
    return lat, lon


# --------------------------------------------------------------------------- #
# Download / clip
# --------------------------------------------------------------------------- #

def clip_dem_around_latlon(
    url: str,
    lat: float,
    lon: float,
    radius_m: float,
    output_npy: Path,
    output_meta: Path,
) -> dict:
    """Stream-clip a square DEM window centred on (lat, lon) via /vsicurl.

    Args:
        url: GDAL /vsicurl path to the remote GeoTIFF.
        lat: Centre latitude, degrees.
        lon: Centre longitude, degrees.
        radius_m: Half-width of the clipped square, metres.
        output_npy: Where to save the elevation crop (float32 array).
        output_meta: Where to save the crop's georeferencing metadata (JSON).

    Returns:
        The metadata dict that was written to output_meta (also handy to
        use immediately, without re-reading the JSON back from disk).
    """
    with rasterio.open(url) as src:
        stereo_crs = CRS.from_wkt(src.crs.to_wkt())
        pixel_size_m = abs(src.transform.a)  # assumes square pixels

        x_m, y_m = latlon_to_projected(lat, lon, stereo_crs)
        inv_transform = ~src.transform
        center_col, center_row = inv_transform * (x_m, y_m)
        center_row, center_col = int(round(center_row)), int(round(center_col))

        half_px = int(round(radius_m / pixel_size_m))
        row_off = max(center_row - half_px, 0)
        col_off = max(center_col - half_px, 0)
        row_stop = min(center_row + half_px, src.height)
        col_stop = min(center_col + half_px, src.width)

        window = Window(col_off, row_off, col_stop - col_off, row_stop - row_off)
        elevation = src.read(1, window=window).astype(np.float32)
        crop_transform = src.window_transform(window)

        # Top-left corner of the crop, in the raster's own projected metres.
        origin_x_m = crop_transform.c
        origin_y_m = crop_transform.f
        projection_wkt = stereo_crs.to_wkt()

    output_npy = Path(output_npy)
    output_npy.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_npy, elevation)

    meta = {
        "pixel_size_m": pixel_size_m,
        "origin_x_m": origin_x_m,
        "origin_y_m": origin_y_m,
        "shape": list(elevation.shape),
        "center_lat": lat,
        "center_lon": lon,
        "radius_m": radius_m,
        "projection_wkt": projection_wkt,
    }
    Path(output_meta).write_text(json.dumps(meta, indent=2))

    print(f"Clipped elevation shape: {elevation.shape}")
    print(f"Saved crop to {output_npy}")
    print(f"Saved metadata to {output_meta}")
    return meta


if __name__ == "__main__":
    meta = clip_dem_around_latlon(URL, LAT, LON, RADIUS_M, Path(OUTPUT), Path(META_OUTPUT))

    # Example: the crater centre itself, as a candidate goal pixel.
    goal_row, goal_col = latlon_to_pixel_in_crop(LAT, LON, meta)
    print(f"Faustini centre (lat={LAT}, lon={LON}) -> pixel (row={goal_row}, col={goal_col})")
