import numpy as np
import rasterio
from rasterio.windows import Window
import matplotlib.pyplot as plt

# ==========================================
# 1. SETUP & LOAD DATA
# ==========================================
DEM_PATH = "Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"
X_START, Y_START = 10000, 20000
WIDTH, HEIGHT = 500, 500
PIXEL_RESOLUTION = 118.0  # meters per pixel

with rasterio.open(DEM_PATH) as src:
    window = Window(X_START, Y_START, WIDTH, HEIGHT)
    dem = src.read(1, window=window).astype(np.float32) * 0.5

# --- MOCK SIMULATION DATA FOR DEMO ---
# (In production, replace this line with your actual 'illumination_fraction' array)
# Creating a dummy array where center is highly illuminated for code execution
y_indices, x_indices = np.indices(dem.shape)
illumination_fraction = np.exp(-((x_indices-250)**2 + (y_indices-250)**2) / 50000)
# ==========================================

print("Calculating terrain slopes...")
# 2. CALCULATE SLOPE MAP FROM DEM (Using Gradients)
# np.gradient returns the change in height per pixel direction
dy, dx = np.gradient(dem, PIXEL_RESOLUTION)
slope_radians = np.arctan(np.sqrt(dx**2 + dy**2))
slope_degrees = np.degrees(slope_radians)

# 3. DEFINE LANDING CONSTRAINT FILTERS
MAX_SAFE_SLOPE = 10.0  # Max degrees your rocket legs can handle
MIN_ILLUMINATION = 0.50  # Must be sunny at least 50% of the time

# Create a binary mask of safe territory (1 = Safe, 0 = Hazard)
safe_terrain_mask = (slope_degrees <= MAX_SAFE_SLOPE) & (illumination_fraction >= MIN_ILLUMINATION)

# 4. COMPUTE SITE SUITABILITY INDEX (SSI)
# Score ranges from 0 (terrible/dangerous) to 1 (perfectly flat and sunny)
# We multiply by the mask so any unsafe slope immediately drops to a score of 0
suitability_index = illumination_fraction * (1.0 - (slope_degrees / slope_degrees.max()))
suitability_index[~safe_terrain_mask] = 0.0  # Wipe out hazard zones

# Find the absolute best single pixel coordinate for touchdown
best_y, best_x = np.unravel_index(np.argmax(suitability_index), suitability_index.shape)
print(f"🥇 Best Landing Site Found at Matrix Coordinates: X={best_x}, Y={best_y}")
print(f" -> Local Slope: {slope_degrees[best_y, best_x]:.2f}°")
print(f" -> Illumination Fraction: {illumination_fraction[best_y, best_x]*100:.1f}%")

# ==========================================
# 5. VISUALIZE THE FINAL LANDING SITE MAP
# ==========================================
fig, ax = plt.subplots(1, 2, figsize=(16, 7))

# Left Plot: Combined Suitability Heatmap
im0 = ax[0].imshow(suitability_index, cmap='viridis', origin='upper')
fig.colorbar(im0, ax=ax[0], label='Landing Suitability Score (0 to 1)')
ax[0].scatter(best_x, best_y, color='red', marker='X', s=200, label='Target Landing Point')
ax[0].set_title("Site Suitability Heatmap\n(Flat + Sunny Zones)")
ax[0].legend()

# Right Plot: Real Terrain Overlay with Hazard Shadows
# Showing the elevation map but graying out unsafe slopes
shaded_dem = dem.copy()
shaded_dem[slope_degrees > MAX_SAFE_SLOPE] = np.nan # Hide steep cliffs

im1 = ax[1].imshow(dem, cmap='gray', origin='upper')
# Overlay unsafe zones in red transparent tint
ax[1].imshow(slope_degrees > MAX_SAFE_SLOPE, cmap='Reds', alpha=0.3, origin='upper', extent=(0, WIDTH, HEIGHT, 0))
ax[1].scatter(best_x, best_y, color='cyan', marker='o', facecolors='none', s=400, linewidths=3, label='Landing Target')
ax[1].set_title("Target Zone Overlaid on DEM Elevation\n(Red Shading = Steep Hazard Slopes)")
ax[1].legend()

plt.tight_layout()
plt.savefig("best_landing_site_map.png", dpi=300)
plt.show()