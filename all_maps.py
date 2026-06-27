import numpy as np
import matplotlib.pyplot as plt
import os

# 1. Load the raw data from your local file
print("Loading local elevation dataset...")
if not os.path.exists("lunar_south_pole_full.npy"):
    raise FileNotFoundError("Could not find 'lunar_south_pole_full.npy'. Please run the download script first.")

elevation_full = np.load("lunar_south_pole_full.npy")

# 2. Downsample for fast processing and plotting (adjust step if you want higher resolution)
step = 10
elevation = elevation_full[::step, ::step]
new_height, new_width = elevation.shape

# Calculate actual horizontal and vertical distance per grid step in meters
# 118.45 meters * step factor
grid_spacing_meters = 118.45 * step

print(f"Processing grid of size {new_height}x{new_width}...")

# 3. Setup the shared Polar Grid Geometry
theta = np.linspace(0, 2 * np.pi, new_width)
r = np.linspace(0, new_height, new_height) * (grid_spacing_meters / 1000.0)  # Convert radius to Kilometers
r = np.flip(r)  # Center (0km) is the South Pole
Theta, R = np.meshgrid(theta, r)

# 4. Calculate Terrain Derivatives (Slope, Aspect, Roughness)
print("Calculating terrain derivatives...")
dy, dx = np.gradient(elevation)

# Slope (Magnitude of the gradient vector)
slope_magnitude = np.sqrt(dx ** 2 + dy ** 2) / grid_spacing_meters
slope_degrees = np.degrees(np.arctan(slope_magnitude))

# Aspect (Direction of the gradient vector in radians, 0 to 2*pi)
aspect_radians = np.arctan2(-dx, dy)
# Adjust domain from [-pi, pi] to [0, 2*pi]
aspect_radians = np.where(aspect_radians < 0, aspect_radians + 2 * np.pi, aspect_radians)

# Roughness (Standard deviation of elevation in a local window)
# We use a simple shortcut: the magnitude of variation in the local gradient
roughness = np.sqrt(dx ** 2 + dy ** 2)

# --- Coordinates for Faustini Crater ---
# Convert 84.3 degrees longitude to radians
lunar_longitude = 77.0
faustini_theta = np.radians(180.0 + lunar_longitude)
# Distance from South Pole (~2.9 degrees of latitude * 30.3 km per degree)
faustini_r = 81.8

# --- Helper Function to Plot and Save ---
def create_polar_map(data, title, filename, cmap, label):
    # Force a new window/figure context
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))
    mesh = ax.pcolormesh(Theta, R, data, cmap=cmap, shading='auto')

    ax.set_theta_zero_location('S')  # South at the bottom
    ax.grid(color='white' if cmap != 'terrain' else 'black', alpha=0.2)

    # Add a clean colorbar
    fig.colorbar(mesh, ax=ax, label=label, orientation='horizontal', pad=0.05)
    plt.title(title, pad=20, fonśtsize=14, fontweight='bold')

    # Add an arrow and label pointing to Faustini Crater
    ax.annotate(
        'Faustini Crater',
        xy=(faustini_theta, faustini_r),  # Where the arrow points (theta, r)
        xytext=(faustini_theta + 0.4, faustini_r + 60),  # Text offset location (theta, r)
        arrowprops=dict(
            facecolor='cyan' if cmap in ['magma', 'inferno'] else 'red',
            shrink=0.05,
            width=2,
            headwidth=8
        ),
        color='white' if cmap in ['magma', 'inferno', 'twilight'] else 'black',
        fontsize=12,
        fontweight='bold',
        bbox=dict(boxstyle="round,pad=0.3", fc="black" if cmap in ['magma', 'inferno'] else "white", alpha=0.6, lw=0)
    )
    plt.title(title, pad=20, fontsize=14, fontweight='bold')
    # Save the file high-res
    output_path = f"{filename}.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")


# --- Window 1: Elevation Map ---
print("Generating Elevation Map...")
create_polar_map(elevation, "Lunar South Pole - Elevation", "elevation", "terrain", "Elevation (meters)")

# --- Window 2: Slope Map ---
print("Generating Slope Map...")
create_polar_map(slope_degrees, "Lunar South Pole - Slope Steepness", "slope", "magma", "Slope (Degrees)")

# --- Window 3: Aspect Map ---
print("Generating Aspect Map...")
create_polar_map(aspect_radians, "Lunar South Pole - Slope Aspect (Direction)", "aspect", "twilight",
                 "Direction (Radians 0 to 2π)")

# --- Window 4: Roughness Map ---
print("Generating Roughness Map...")
create_polar_map(roughness, "Lunar South Pole - Surface Roughness", "roughness", "inferno",
                 "Local Elevation Variability")

# 5. Show all windows simultaneously
print("Displaying all map windows. Close windows to finish script execution.")
plt.show()