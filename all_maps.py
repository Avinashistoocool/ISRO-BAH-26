import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter
from matplotlib.colors import LightSource, rgb_to_hsv, hsv_to_rgb

INPUT = "lunar_south_pole_full.npy"


def compute_slope(dem):
    gy, gx = np.gradient(dem)
    return np.sqrt(gx**2 + gy**2)


def compute_roughness(dem):
    smooth = gaussian_filter(dem, sigma=2)
    return np.abs(dem - smooth)


def normalize(x):
    x = np.nan_to_num(x)
    return (x - x.min()) / (x.max() - x.min() + 1e-8)


def plot_all(dem, slope, roughness):

    ls = LightSource(azdeg=315, altdeg=45)

    dem_norm = normalize(dem)

    # base color (pure elevation colormap)
    elevation_rgb = plt.cm.terrain(dem_norm)[..., :3]

    # hillshade (grayscale lighting)
    hillshade = ls.hillshade(dem, vert_exag=2)
    hillshade = normalize(hillshade)

    # -----------------------------
    # HSV-based lighting (correct method)
    # -----------------------------
    hsv = rgb_to_hsv(elevation_rgb)

    # ONLY modify brightness/value channel
    hsv[..., 2] = hsv[..., 2] * (0.4 + 0.6 * hillshade)

    shaded_rgb = hsv_to_rgb(hsv)

    # -----------------------------
    # FEATURES
    # -----------------------------
    slope_n = normalize(slope)
    rough_n = normalize(roughness)

    # -----------------------------
    # PLOTS
    # -----------------------------
    fig = plt.figure(figsize=(16, 10))

    ax1 = fig.add_subplot(2, 2, 1)
    ax1.set_title("Elevation (Pure Color)")
    ax1.imshow(elevation_rgb)
    ax1.axis("off")

    ax2 = fig.add_subplot(2, 2, 2)
    ax2.set_title("Hillshade (Lighting Only)")
    ax2.imshow(hillshade, cmap="gray")
    ax2.axis("off")

    ax3 = fig.add_subplot(2, 2, 3)
    ax3.set_title("Shaded Relief (Correct HSV Method)")
    ax3.imshow(shaded_rgb)
    ax3.axis("off")

    ax4 = fig.add_subplot(2, 2, 4)
    ax4.set_title("Slope + Roughness (Mean View)")
    ax4.imshow((slope_n + rough_n) / 2, cmap="magma")
    ax4.axis("off")

    plt.tight_layout()
    plt.show()


def main():
    dem = np.load(INPUT)

    slope = compute_slope(dem)
    roughness = compute_roughness(dem)

    plot_all(dem, slope, roughness)


if __name__ == "__main__":
    main()