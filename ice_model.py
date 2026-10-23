"""
ice_model.py
============

Probabilistic water-ice distribution model for the DEM crop (Faustini region).

Model: naive-Bayes evidence fusion in log-odds space, gated by thermal physics.

    logit P(ice) = prior
                 + w_cpr   * z(radar CPR anomaly, roughness-corrected)
                 + w_lamp  * z(LAMP off/on-band ratio)
                 + w_psr   * PSR
                 + w_dfsar * z(DFSAR CPR anomaly) - w_dop * z(DFSAR DOP)   [if available]
    P(ice | data) = P(thermally stable) * sigmoid(logit)

Why roughness-corrected CPR: high CPR also comes from rocky / rough terrain,
not just ice. We fit CPR ~ terrain roughness on *warm* pixels (Tmax > 150 K,
where ice cannot survive) and use the residual in cold pixels as evidence.

Thermal gate: Diviner Tmax < ~110 K means surface ice is stable. A finite
depth-to-ice-stability (Schorghofer & Williams 2020) means subsurface ice is
stable within the top ~0.5 m.

Weight uncertainty is propagated by Monte-Carlo sampling of the weights. The
output is a mean probability map and a standard-deviation map.

Run:
    python ice_data.py     # once, to fetch the evidence layers
    python ice_model.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.ndimage import uniform_filter

import dfsar
from ice_data import load_grid, load_layers

OUT_DIR = Path("outputs")

# Prior log-odds and (mean, std) of the evidence weights. The std values are
# deliberately wide because there are no ground-truth labels for calibration.
PRIOR_LOGIT = -1.5
WEIGHTS: Dict[str, Tuple[float, float]] = {
    "cpr": (0.8, 0.3),
    "lamp": (0.5, 0.25),
    "psr": (1.5, 0.5),
    "dfsar_cpr": (1.2, 0.4),
    "dfsar_dop": (0.8, 0.3),
}
T_STABLE_K = 110.0      # surface ice stability temperature
T_SOFTNESS_K = 5.0      # width of the sigmoid around T_STABLE_K
RADAR_SCALE_M = 120.0   # Mini-RF resolution; terrain roughness is computed at this scale
N_SAMPLES = 64

# Column-ice assumptions for the volume estimate (top 5 m of regolith).
COLUMN_DEPTH_M = 5.0
L_SENSING_M = 3.0
ICE_VOL_FRACTION = (0.01, 0.05, 0.10)  # low / mid / high


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def robust_z(x: np.ndarray, ref_mask: Optional[np.ndarray] = None) -> np.ndarray:
    """(x - median) / (1.4826 * MAD), computed on ref_mask pixels. NaN -> 0."""
    ref = x[np.isfinite(x) & (ref_mask if ref_mask is not None else True)]
    med = np.median(ref)
    mad = 1.4826 * np.median(np.abs(ref - med)) + 1e-9
    return np.nan_to_num((x - med) / mad, nan=0.0)


def nan_smooth(x: np.ndarray, size: float) -> np.ndarray:
    """Boxcar mean ignoring NaNs; NaN where less than half the window is valid."""
    k = max(int(round(size)), 1)
    m = np.isfinite(x)
    num = uniform_filter(np.where(m, x, 0.0).astype(np.float64), k)
    den = uniform_filter(m.astype(np.float64), k)
    return np.where(den > 0.5, num / np.maximum(den, 1e-9), np.nan).astype(np.float32)


# --------------------------------------------------------------------------- #
# Terrain
# --------------------------------------------------------------------------- #

def terrain_roughness(dem: np.ndarray, pixel_size_m: float, scale_m: float) -> np.ndarray:
    """RMS slope (deg) inside a scale_m window, matching the radar footprint."""
    gy, gx = np.gradient(dem, pixel_size_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    k = max(int(round(scale_m / pixel_size_m)), 1)
    return np.sqrt(uniform_filter(slope ** 2, size=k)).astype(np.float32)


# --------------------------------------------------------------------------- #
# Evidence layers
# --------------------------------------------------------------------------- #

def thermal_stability(tmax: np.ndarray, ice_depth: Optional[np.ndarray]) -> np.ndarray:
    """P(ice thermally stable). Surface: Tmax sigmoid. Subsurface: finite depth-to-ice."""
    surface = sigmoid((T_STABLE_K - tmax) / T_SOFTNESS_K)
    if ice_depth is None:
        return surface
    # The depth-to-stability product is finite over most of the region (ice can be
    # stable a few cm down even beside PSRs), so it is a soft, capped term: shallow
    # stability depth -> higher chance, never as strong as a cold surface.
    subsurface = np.where(np.isfinite(ice_depth), 0.6 * np.exp(-np.nan_to_num(ice_depth) / 0.05), 0.0)
    return np.maximum(surface, subsurface).astype(np.float32)


def cpr_anomaly(cpr: np.ndarray, roughness: np.ndarray, tmax: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Roughness-corrected CPR z-score.

    Fits log(CPR) = a + b * roughness on warm (ice-free) pixels and returns the
    standardised residual everywhere, plus the fitted coefficients.
    """
    log_cpr = np.log(np.clip(cpr, 1e-3, None)).astype(np.float64)
    rough = roughness.astype(np.float64)
    warm = np.isfinite(log_cpr) & np.isfinite(rough) & (tmax > 150.0)
    # Fit on per-bin medians: robust to outliers and well-conditioned.
    edges = np.percentile(rough[warm], np.linspace(0, 100, 21))
    idx = np.digitize(rough[warm], edges[1:-1])
    xs = np.array([np.median(rough[warm][idx == i]) for i in range(20)])
    ys = np.array([np.median(log_cpr[warm][idx == i]) for i in range(20)])
    b, a = np.polyfit(xs, ys, 1)
    resid = log_cpr - (a + b * rough)
    return robust_z(resid, warm).astype(np.float32), np.array([a, b])


def lamp_evidence(ratio: np.ndarray) -> np.ndarray:
    """LAMP off/on-band ratio > 1 suggests surface frost. Raw product is noisy; clip & smooth."""
    r = np.where((ratio > 0) & (ratio < 10), ratio, np.nan)
    z = robust_z(np.log(r))
    return np.clip(uniform_filter(z, size=12), -3, 3)  # ~240 m smoothing at 20 m/px


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

def build_evidence(layers: Dict) -> Dict[str, np.ndarray]:
    rough = terrain_roughness(layers["dem"], layers["pixel_size_m"], RADAR_SCALE_M)
    tmax = layers["tmax"]
    ev: Dict[str, np.ndarray] = {
        "stability": thermal_stability(tmax, layers.get("ice_depth")),
        "roughness": rough,
        "psr": np.nan_to_num(layers["psr"]).astype(np.float32),
    }
    if layers.get("cpr_s") is not None:
        ev["cpr"], ev["cpr_fit"] = cpr_anomaly(layers["cpr_s"], rough, tmax)
    if layers.get("lamp_ratio") is not None:
        ev["lamp"] = lamp_evidence(layers["lamp_ratio"])
    # DFSAR (ISRO PRADAN) — used automatically once ice_data.py has warped it.
    # DFSAR SERD (high = smooth) explains ~75% of L-band CPR variance vs ~0.5% for
    # DEM roughness, so when available it replaces DEM roughness as the baseline
    # covariate. Everything is smoothed to the Mini-RF ~120 m footprint.
    radar_rough = rough
    if layers.get("dfsar_serd_l") is not None:
        radar_rough = -nan_smooth(layers["dfsar_serd_l"], RADAR_SCALE_M / layers["pixel_size_m"])
        ev["radar_rough_source"] = "dfsar_serd"
    dfsar_cpr = layers.get("dfsar_cpr_l") if layers.get("dfsar_cpr_l") is not None else layers.get("dfsar_cpr_s")
    if dfsar_cpr is not None:
        z, ev["dfsar_cpr_fit"] = cpr_anomaly(
            nan_smooth(dfsar_cpr, RADAR_SCALE_M / layers["pixel_size_m"]), radar_rough, tmax)
        # Only fuse if cold pixels show a higher CPR anomaly than warm (ice-free) ones.
        shift = float(z[tmax < 110].mean() - z[tmax > 150].mean())
        ev["dfsar_cpr_cold_minus_warm_z"] = shift
        if shift > 0:
            ev["dfsar_cpr"] = z
    dfsar_dop = layers.get("dfsar_dop_l") if layers.get("dfsar_dop_l") is not None else layers.get("dfsar_dop_s")
    if dfsar_dop is not None:
        ev["dfsar_dop"] = robust_z(dfsar_dop)
    # Dual-frequency depth inversion: DFSAR L + (DFSAR S, else Mini-RF S; both 12.6 cm).
    cpr_l = layers.get("dfsar_cpr_l")
    cpr_s = layers.get("dfsar_cpr_s") if layers.get("dfsar_cpr_s") is not None else layers.get("cpr_s")
    if cpr_l is not None and cpr_s is not None:
        k = RADAR_SCALE_M / layers["pixel_size_m"]
        ev["dfsar_depth"] = dfsar.dual_band_depth(
            nan_smooth(cpr_l, k), nan_smooth(cpr_s, k), radar_rough, tmax,
            layers.get("dfsar_dop_l"), layers.get("dfsar_dop_s"))
        ev["dfsar_depth"]["info"]["s_band_source"] = (
            "dfsar" if layers.get("dfsar_cpr_s") is not None else "mini-rf")
    return ev


def ice_probability(ev: Dict[str, np.ndarray], n_samples: int = N_SAMPLES,
                    seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """Monte-Carlo over weights -> (mean P(ice), std P(ice))."""
    rng = np.random.default_rng(seed)
    terms = {k: ev[k] for k in WEIGHTS if k in ev}
    sign = {"dfsar_dop": -1.0}  # low DOP = volume scattering = ice-like
    mean = np.zeros_like(ev["stability"], dtype=np.float64)
    sq = np.zeros_like(mean)
    for _ in range(n_samples):
        logit = np.full(mean.shape, PRIOR_LOGIT)
        for k, x in terms.items():
            mu, sd = WEIGHTS[k]
            logit += sign.get(k, 1.0) * max(rng.normal(mu, sd), 0.0) * x
        p = ev["stability"] * sigmoid(logit)
        mean += p
        sq += p * p
    mean /= n_samples
    std = np.sqrt(np.maximum(sq / n_samples - mean ** 2, 0.0))
    return mean.astype(np.float32), std.astype(np.float32)


def ice_volume(prob: np.ndarray, pixel_size_m: float, ice_depth: Optional[np.ndarray],
               dfsar_depth: Optional[np.ndarray] = None) -> Dict:
    """Expected ice volume (m^3) in the top COLUMN_DEPTH_M, for low/mid/high ice fractions.

    Ice-table depth: the DFSAR L/S inversion where it detects ice, otherwise
    Diviner depth-to-stability. The volume is split into the part L-band
    senses directly (<= L_SENSING_M) and the extrapolated part below that.
    """
    area = pixel_size_m ** 2
    top = np.nan_to_num(ice_depth, nan=COLUMN_DEPTH_M) if ice_depth is not None else np.zeros_like(prob)
    source = "diviner"
    if dfsar_depth is not None:
        top = np.where(np.isfinite(dfsar_depth), dfsar_depth, top)
        source = "dfsar+diviner"
    top = np.clip(top, 0.0, COLUMN_DEPTH_M)
    direct = np.clip(L_SENSING_M - top, 0.0, None)
    extrap = COLUMN_DEPTH_M - np.maximum(top, L_SENSING_M)
    v_direct = float(np.sum(prob * area * direct))
    v_extrap = float(np.sum(prob * area * extrap))
    return {
        "column_depth_m": COLUMN_DEPTH_M,
        "ice_table_depth_source": source,
        "ice_area_km2_p>0.5": float((prob > 0.5).sum() * area / 1e6),
        f"expected_volume_m3_direct_0-{L_SENSING_M:g}m": {f"f_ice={f:.2f}": v_direct * f for f in ICE_VOL_FRACTION},
        f"expected_volume_m3_extrapolated_{L_SENSING_M:g}-{COLUMN_DEPTH_M:g}m": {f"f_ice={f:.2f}": v_extrap * f for f in ICE_VOL_FRACTION},
        "note": "Ice-table depth uses DFSAR L/S only when the depth signal passes the enrichment test; "
                "otherwise Diviner depth-to-stability. Below L-band sensing depth is extrapolated.",
    }


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def save_geotiff(path: Path, arr: np.ndarray) -> None:
    import rasterio
    grid = load_grid()
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype="float32", crs=grid["crs"], transform=grid["transform"],
                       nodata=np.nan, compress="deflate") as dst:
        dst.write(arr.astype(np.float32), 1)


def plot(ev: Dict, prob: np.ndarray, std: np.ndarray, out_png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = [
        ("Thermal stability P", ev["stability"], "Blues", (0, 1)),
        ("Radar CPR anomaly (z)", ev.get("cpr"), "RdBu_r", (-3, 3)),
        ("LAMP frost evidence (z)", ev.get("lamp"), "RdBu_r", (-3, 3)),
        ("PSR", ev["psr"], "gray_r", (0, 1)),
        ("P(ice) mean", prob, "viridis", (0, 1)),
        ("P(ice) std (uncertainty)", std, "magma", None),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    for ax, (title, arr, cmap, lim) in zip(axes.ravel(), panels):
        ax.set_title(title)
        ax.axis("off")
        if arr is None:
            ax.text(0.5, 0.5, "not available", ha="center", transform=ax.transAxes)
            continue
        im = ax.imshow(arr, cmap=cmap, vmin=lim[0] if lim else None, vmax=lim[1] if lim else None)
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle("Faustini region ice-distribution model (60 x 60 km, 20 m/px)")
    plt.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def plot_depth(d: Dict, prob: np.ndarray, out_png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    cls = np.ma.masked_equal(d["class"], dfsar.NO_DATA)
    im = axes[0].imshow(cls, cmap=ListedColormap(["#222", "#3cb4ff", "#ffb000", "#e0245e"]),
                        vmin=-0.5, vmax=3.5, interpolation="nearest")
    cb = fig.colorbar(im, ax=axes[0], ticks=range(4), fraction=0.046)
    cb.ax.set_yticklabels([dfsar.CLASS_NAMES[i] for i in range(4)])
    axes[0].set_title("DFSAR L/S detection class")
    depth = np.where(prob > 0.3, d["depth_m"], np.nan)
    im = axes[1].imshow(depth, cmap="viridis_r", vmin=0, vmax=dfsar.D_MAX_M)
    fig.colorbar(im, ax=axes[1], fraction=0.046, label="m")
    axes[1].set_title("Depth to ice top (P(ice) > 0.3)")
    im = axes[2].imshow(np.where(prob > 0.3, d["depth_std_m"], np.nan), cmap="magma")
    fig.colorbar(im, ax=axes[2], fraction=0.046, label="m")
    axes[2].set_title("Depth uncertainty (1 sigma)")
    for ax in axes:
        ax.axis("off")
    plt.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    layers = load_layers()
    ev = build_evidence(layers)
    prob, std = ice_probability(ev)

    np.save(OUT_DIR / "ice_probability.npy", prob)
    np.save(OUT_DIR / "ice_probability_std.npy", std)
    save_geotiff(OUT_DIR / "ice_probability_map.tif", prob)
    plot(ev, prob, std, OUT_DIR / "ice_probability.png")

    d = ev.get("dfsar_depth")
    if d is not None:
        save_geotiff(OUT_DIR / "ice_depth_m.tif", d["depth_m"])
        save_geotiff(OUT_DIR / "ice_depth_std_m.tif", d["depth_std_m"])
        save_geotiff(OUT_DIR / "ice_depth_class.tif", d["class"].astype(np.float32))
        plot_depth(d, prob, OUT_DIR / "ice_depth.png")

    summary = {
        "evidence_used": [k for k in WEIGHTS if k in ev] + (["dfsar_depth"] if d is not None else []),
        "cpr_roughness_fit_log_cpr=a+b*rough": ev.get("cpr_fit", np.array([])).tolist(),
        "dfsar_cpr_cold_minus_warm_z": ev.get("dfsar_cpr_cold_minus_warm_z"),
        "mean_p_in_psr": float(prob[ev["psr"] > 0.5].mean()),
        "mean_p_outside_psr": float(prob[ev["psr"] < 0.5].mean()),
        "volume": ice_volume(prob, layers["pixel_size_m"], layers.get("ice_depth"),
                             d["depth_m"] if d is not None and d["info"]["depth_signal_significant"] else None),
    }
    if d is not None:
        area_km2 = layers["pixel_size_m"] ** 2 / 1e6
        summary["dfsar_depth"] = {
            **d["info"],
            "area_km2_by_class": {dfsar.CLASS_NAMES[i]: float((d["class"] == i).sum() * area_km2) for i in range(4)},
            "median_depth_m_where_p>0.5": float(np.nanmedian(np.where(prob > 0.5, d["depth_m"], np.nan))),
        }
    with (OUT_DIR / "ice_volume_estimate.json").open("w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
