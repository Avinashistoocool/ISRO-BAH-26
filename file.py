import rasterio
from rasterio.windows import Window
import numpy as np
from tqdm import tqdm

url = "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"

print("Connecting to USGS server...")
with rasterio.open(url) as src:
    total_width = src.width
    total_height = src.height

    # Define the 2000-pixel strip at the bottom
    height_chunk = 2000
    row_offset = total_height - height_chunk

    # Initialize the array to store the FULL resolution width data
    # We use float32 because applying the 0.5 multiplier converts integers to decimals
    south_pole_strip = np.zeros((height_chunk, total_width), dtype=np.float32)

    print(f"Streaming full-resolution South Pole region ({height_chunk}x{total_width} pixels)...")

    # Read row-by-row to show progress and manage network stability
    for i, r_idx in enumerate(tqdm(range(row_offset, total_height), desc="Downloading Rows")):
        row_window = Window(0, r_idx, total_width, 1)

        # Read the row at full resolution (no downsampling)
        row_data = src.read(1, window=row_window)

        # Mask out NoData values and apply the USGS scaling factor (0.5) right away
        masked_row = np.ma.masked_equal(row_data[0], src.nodata)
        elevation_row = masked_row * 0.5

        # Save to our master array
        south_pole_strip[i, :] = elevation_row

# Save the array to your local hard drive
output_filename = "lunar_south_pole_full.npy"
print(f"Saving data locally to '{output_filename}'...")
np.save(output_filename, south_pole_strip)
print("Done! You can now close this script.")