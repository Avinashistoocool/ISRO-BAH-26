"""
ice_data.py
===========

Fetches every evidence layer used by ice_model.py and resamples it onto the
DEM crop grid described by lunar_south_pole_full_meta.json (20 m/px, Moon
south-polar stereographic). Results are cached as .npy in data/processed/.

All sources are public (no login) and streamed with GDAL /vsicurl, so only the
window covering the crop is downloaded.

Chandrayaan-2 DFSAR is not public without an ISSDC PRADAN account. Until it is
available, LRO Mini-RF S-band CPR is used as the radar layer. Drop DFSAR
GeoTIFFs into data/raw/ (see DFSAR_FILES) and they are picked up automatically.

Run:
    python ice_data.py            # fetch all layers (skips cached ones)
    python ice_data.py --force    # re-download everything
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("PROJ_IGNORE_CELESTIAL_BODY", "YES")

META_PATH = Path("lunar_south_pole_full_meta.json")
DEM_PATH = Path("lunar_south_pole_full.npy")
PROCESSED = Path("data/processed")
RAW = Path("data/raw")

# Every source below is in the same sphere-based (R = 1737.4 km) south-polar
# stereographic projection as the LOLA 20 m DEM.
_PGDA = "/vsicurl/https://pgda.gsfc.nasa.gov/data"
_DIVINER = "/vsicurl/https://luna1.diviner.ucla.edu/~jpierre/diviner/level4_polar"
SOURCES: Dict[str, Dict] = {
    # LOLA 20 m permanently-shadowed-region map (Barker et al.), same grid as DEM.
    "psr": {
        "url": f"{_PGDA}/LOLA_20mpp/LPSR_80S_20MPP_ADJ.TIF",
        "resampling": Resampling.nearest,
    },
    # LOLA average solar visibility, 85-90S, 60 m (Mazarico et al. 2011).
    "illumination": {
        "url": f"{_PGDA}/MoonIllumination/AVGVISIB_85S_060M_201608.TIF",
        "resampling": Resampling.bilinear,
    },
    # Diviner south-polar summer maximum surface temperature (Williams et al.
    # 2019). At the south pole this is effectively the annual maximum.
    "tmax": {
        "url": f"{_DIVINER}/additional_maps/polar_south_80_summer_max-float.tif",
        "resampling": Resampling.bilinear,
    },
    # Diviner depth to ice stability (m) (Schorghofer & Williams 2020).
    "ice_depth": {
        "url": f"{_DIVINER}/24x6_240m/additional_maps/polar_south_80_zit_float32.tif",
        "resampling": Resampling.bilinear,
    },
    # LRO Mini-RF S-band (12.6 cm) circular polarisation ratio, 118 m.
    "cpr_s": {
        "url": "/vsicurl/https://pds-geosciences.wustl.edu/lro/lro-l-mrflro-4-cdr-v1/"
               "lromrf_0005/data/sar/mosaics/lsz_xxxxx_3cp_piu_90s000_v1.lbl",
        "resampling": Resampling.average,
    },
    # LRO LAMP Lyman-alpha off-band/on-band albedo ratio, 240 m (Gladstone 2012).
    "lamp_ratio": {
        "url": "/vsicurl/https://planetarydata.jpl.nasa.gov/img/data/lro/lamp/gdr/"
               "LROLAM_2001/DATA/RATIO/LAMP_80s_240mpp_ratio_albed_01.lbl",
        "resampling": Resampling.bilinear,
    },
}

# Optional DFSAR layers (GeoTIFF, any projection GDAL can read).
# Level-3C polar mosaics (PRADAN, L-band full-pol, 25 m) are extracted into
# data/raw/dfsar/; per-strip or MIDAS-derived rasters can use the flat names.
_L3C = RAW / "dfsar" / "data" / "derived"


def _first(*candidates: Path) -> Path:
    for pattern in candidates:
        if "*" in str(pattern):
            hits = sorted(RAW.glob(str(pattern.relative_to(RAW)).replace("\\", "/")))
        else:
            hits = [pattern]
        for h in hits:
            if h.exists():
                return h
    return candidates[0]


DFSAR_FILES = {
    "dfsar_cpr_l": _first(RAW / "dfsar_cpr_L.tif", _L3C / "*" / "*speast_d_cpr_*.tif", _L3C / "*" / "*spwest_d_cpr_*.tif"),
    "dfsar_cpr_s": RAW / "dfsar_cpr_S.tif",
    "dfsar_dop_l": RAW / "dfsar_dop_L.tif",
    "dfsar_dop_s": RAW / "dfsar_dop_S.tif",
    # SERD: high = smooth surface (roughness descriptor independent of DEM).
    "dfsar_serd_l": _first(_L3C / "*" / "*speast_d_srd_*.tif", _L3C / "*" / "*spwest_d_srd_*.tif"),
    # T-ratio: increases with dielectric constant.
    "dfsar_trt_l": _first(_L3C / "*" / "*speast_d_trt_*.tif", _L3C / "*" / "*spwest_d_trt_*.tif"),
}


def load_grid(meta_path: Path = META_PATH) -> Dict:
    """Target grid (shape, affine transform, CRS) of the DEM crop."""
    with meta_path.open() as f:
        meta = json.load(f)
    rows, cols = meta["shape"]
    transform = from_origin(meta["origin_x_m"], meta["origin_y_m"],
                            meta["pixel_size_m"], meta["pixel_size_m"])
    return {"shape": (rows, cols), "transform": transform,
            "crs": CRS.from_wkt(meta["projection_wkt"]), "meta": meta}


def warp_to_grid(path: str, grid: Dict, resampling: Resampling) -> np.ndarray:
    """Read `path` and resample band 1 onto `grid`. Nodata becomes NaN."""
    dst = np.full(grid["shape"], np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        src_nodata = src.nodata
        # Read only the source window covering the target (keeps /vsicurl cheap).
        left, top = grid["transform"] * (0, 0)
        right, bottom = grid["transform"] * (grid["shape"][1], grid["shape"][0])
        pad = 4 * max(abs(src.res[0]), abs(src.res[1]))
        win = src.window(left - pad, bottom - pad, right + pad, top + pad)
        win = win.round_offsets().round_lengths().intersection(
            rasterio.windows.Window(0, 0, src.width, src.height))
        data = src.read(1, window=win).astype(np.float32)
        if src_nodata is not None:
            data[np.isclose(data, src_nodata) | (data < -1e30)] = np.nan
        scale = src.scales[0] if src.scales else 1.0
        offset = src.offsets[0] if src.offsets else 0.0
        data = data * scale + offset
        reproject(
            source=data,
            destination=dst,
            src_transform=src.window_transform(win),
            src_crs=src.crs or grid["crs"],
            src_nodata=np.nan,
            dst_transform=grid["transform"],
            dst_crs=grid["crs"],
            dst_nodata=np.nan,
            resampling=resampling,
        )
    return dst


def fetch_all(force: bool = False) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    grid = load_grid()
    for name, spec in SOURCES.items():
        out = PROCESSED / f"{name}.npy"
        if out.exists() and not force:
            print(f"[cached] {name}")
            continue
        print(f"[fetch ] {name} <- {spec['url'].split('/')[-1]}")
        arr = warp_to_grid(spec["url"], grid, spec["resampling"])
        np.save(out, arr)
        print(f"         valid={np.isfinite(arr).mean():.1%} "
              f"min={np.nanmin(arr):.4g} max={np.nanmax(arr):.4g}")
    for name, path in DFSAR_FILES.items():
        out = PROCESSED / f"{name}.npy"
        if path.exists() and (force or not out.exists()):
            print(f"[dfsar ] {name} <- {path.name}")
            arr = warp_to_grid(str(path), grid, Resampling.average)
            np.save(out, arr)
            print(f"         valid={np.isfinite(arr).mean():.1%}")


def load_layers() -> Dict[str, Optional[np.ndarray]]:
    """Load DEM + all cached layers. Missing optional layers are None."""
    layers: Dict[str, Optional[np.ndarray]] = {"dem": np.load(DEM_PATH)}
    for name in list(SOURCES) + list(DFSAR_FILES):
        p = PROCESSED / f"{name}.npy"
        layers[name] = np.load(p) if p.exists() else None
    layers["pixel_size_m"] = load_grid()["meta"]["pixel_size_m"]
    return layers


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--force", action="store_true", help="re-download cached layers")
    fetch_all(ap.parse_args().force)
