import os
import rasterio
import numpy as np
from rasterio.windows import from_bounds
from pyproj import Transformer

# =========================
# CONFIG
# =========================
URL = "/vsicurl/https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF"

LAT = -87.85
LON = 82.0

RADIUS_M = 30000   # change this for region size
OUTPUT = "lunar_south_pole_full.npy"


def load_dem_region():

    # needed for lunar CRS handling
    os.environ["PROJ_IGNORE_CELESTIAL_BODY"] = "YES"

    print("Opening lunar DEM...")

    with rasterio.open(URL) as src:

        # transform lat/lon → dataset CRS
        transformer = Transformer.from_crs(
            "EPSG:4326",
            src.crs,
            always_xy=True
        )

        x, y = transformer.transform(LON, LAT)

        # crop window
        window = from_bounds(
            x - RADIUS_M,
            y - RADIUS_M,
            x + RADIUS_M,
            y + RADIUS_M,
            src.transform
        )

        dem = src.read(1, window=window).astype(np.float32)

        # handle nodata
        if src.nodata is not None:
            dem = np.where(dem == src.nodata, np.nan, dem)

        # apply scaling if present
        if src.scales and src.scales[0]:
            dem *= src.scales[0]

    np.save(OUTPUT, dem)

    print("Saved:", OUTPUT)
    print("Shape:", dem.shape)

    return dem


if __name__ == "__main__":
    load_dem_region()