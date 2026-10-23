import rasterio
from rasterio.windows import Window
import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm

url = "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"

with rasterio.open(url) as src:
    total_width = src.width
    total_height = src.height

    # Target the bottom region
    height_chunk = 2000
    row_offset = total_height - height_chunk

    # Define downsampling factors (reading every 10th pixel)
    step = 1
    new_height = height_chunk // step
    new_width = total_width // step

    # Initialize an empty array to hold our downsampled data
    south_pole_strip = np.zeros((new_height, new_width), dtype=src.dtypes[0])

    print("Streaming and downsampling Lunar South Pole data...")

    # Loop through the rows with a progress bar
    for i, r_idx in enumerate(tqdm(range(row_offset, total_height, step), desc="Downloading Rows")):
        # Read a window that is 1 pixel high, spanning the full width
        row_window = Window(0, r_idx, total_width, 1)

        # Read the row and downsample its width on the fly (returns a 2D array)
        row_data = src.read(1, window=row_window, out_shape=(1, new_width))

        # Save it into our master array (row_data is 2D, so we extract the first row)
        south_pole_strip[i, :] = row_data[0, :]

# Handle NoData and scale to meters
south_pole_strip = np.ma.masked_equal(south_pole_strip, src.nodata)
elevation = south_pole_strip * 0.5

# Setup the Polar grid
theta = np.linspace(0, 2 * np.pi, new_width)
r = np.linspace(0, new_height, new_height)
r = np.flip(r)
Theta, R = np.meshgrid(theta, r)

# Plotting
fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))
mesh = ax.pcolormesh(Theta, R, elevation, cmap='viridis', shading='auto')
ax.set_theta_zero_location('S')
ax.set_yticklabels([])
ax.grid(color='white', alpha=0.2)

fig.colorbar(mesh, ax=ax, label='Elevation (meters)', orientation='horizontal', pad=0.05)
plt.title("Lunar South Pole (Streamed with Progress Bar)", pad=20)
plt.show()