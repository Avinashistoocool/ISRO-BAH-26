"""
dfsar.py
========

Chandrayaan-2 DFSAR dual-frequency (L + S band) processing:

1. Polarimetry: CPR / DOP from compact-pol (LH, LV) or full-pol (HH, HV, VV)
   single-look-complex channels, with boxcar multilooking.
2. Depth-to-ice inversion from the L/S CPR excess ratio.

Depth inversion
---------------
The ice-related CPR excess of band b (CPR above the rough-terrain baseline) is
modelled as an ice layer whose top is at depth D, seen through a dry regolith
lag. Band b's sensitivity decays exponentially with depth, with e-folding
depth delta_b:

    e_b = A * k_b * exp(-D / delta_b)

Taking the ratio of the two bands cancels the unknown ice amount A:

    R = e_L / e_S = k * exp(D * (1/delta_S - 1/delta_L))
    D = ln(R / k) / (1/delta_S - 1/delta_L)

k = k_L / k_S is the band scattering-efficiency ratio. It is calibrated on
pixels where Diviner says surface ice is stable (D ~ 0), so then R ~ k.
Noise is propagated by Monte-Carlo sampling of e_L and e_S.

If only L-band detects ice, the ice is deeper than S-band can see, so D is
reported near its maximum. If only S-band detects it, the signal is
physically inconsistent (usually roughness or a calibration problem) and the
pixel is flagged.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
from scipy.ndimage import uniform_filter

# e-folding sensing depths (m). Sensing depth ~2 e-folds: S ~1 m, L ~3 m.
DELTA_M = {"S": 0.5, "L": 1.5}
D_MAX_M = 5.0
DETECT_Z = 3.0          # excess must exceed DETECT_Z * noise sigma
DOP_ICE_MAX = 0.13      # volume scattering threshold from the problem statement
CALIB_TMAX_K = 100.0    # surface ice stable -> D ~ 0 for k calibration
MIN_CALIB_PX = 200
MIN_ENRICHMENT = 2.0    # cold/warm detection-rate ratio needed to trust the depth map

CLASS_NAMES = {0: "none", 1: "near-surface (L+S)", 2: "deep (L only)", 3: "S only (inconsistent)"}
NO_DATA = 255


# --------------------------------------------------------------------------- #
# Polarimetry
# --------------------------------------------------------------------------- #

def _ml(x: np.ndarray, looks: Tuple[int, int]) -> np.ndarray:
    return uniform_filter(x, size=looks)


def compact_pol_cpr_dop(e_h: np.ndarray, e_v: np.ndarray,
                        looks: Tuple[int, int] = (5, 1)) -> Tuple[np.ndarray, np.ndarray]:
    """Hybrid-pol (circular transmit, linear H/V receive) -> (CPR, DOP).

    Stokes vector of the received wave (Raney 2007):
        S1 = <|E_H|^2 + |E_V|^2>, S2 = <|E_H|^2 - |E_V|^2>,
        S3 = 2 Re<E_H E_V*>,      S4 = -2 Im<E_H E_V*>
    CPR = (S1 - S4) / (S1 + S4),  DOP = sqrt(S2^2 + S3^2 + S4^2) / S1
    For left-circular transmit, flip the sign of S4. `looks` is (azimuth, range).
    """
    hh = np.abs(e_h) ** 2
    vv = np.abs(e_v) ** 2
    hv = e_h * np.conj(e_v)
    s1 = _ml(hh + vv, looks)
    s2 = _ml(hh - vv, looks)
    s3 = _ml(2 * hv.real, looks)
    s4 = _ml(-2 * hv.imag, looks)
    cpr = (s1 - s4) / np.maximum(s1 + s4, 1e-12)
    dop = np.sqrt(s2 ** 2 + s3 ** 2 + s4 ** 2) / np.maximum(s1, 1e-12)
    return cpr.astype(np.float32), np.clip(dop, 0, 1).astype(np.float32)


def full_pol_cpr(s_hh: np.ndarray, s_hv: np.ndarray, s_vv: np.ndarray,
                 looks: Tuple[int, int] = (5, 1)) -> np.ndarray:
    """Full-pol linear-basis SLC -> CPR = same-sense / opposite-sense circular power.

    With reciprocity (S_HV = S_VH):
        S_same = (S_HH - S_VV + 2j S_HV) / 2
        S_opp  = j (S_HH + S_VV) / 2
    """
    same = _ml(np.abs(s_hh - s_vv + 2j * s_hv) ** 2, looks)
    opp = _ml(np.abs(s_hh + s_vv) ** 2, looks)
    return (same / np.maximum(opp, 1e-12)).astype(np.float32)


def multilook_factor(pixel_spacing: float, line_spacing: float, incidence_deg: float) -> int:
    """Azimuth looks for ~square ground pixels (ISRO MIDAS convention); range looks = 1."""
    return max(int(round(pixel_spacing / (line_spacing * np.sin(np.radians(incidence_deg))))), 1)


# --------------------------------------------------------------------------- #
# Ice signal per band
# --------------------------------------------------------------------------- #

def cpr_excess(cpr: np.ndarray, roughness: np.ndarray, warm: np.ndarray) -> Tuple[np.ndarray, float, np.ndarray]:
    """Linear CPR above the rough-terrain baseline, fitted on warm (ice-free) pixels.

    Returns (excess, noise_sigma, [a, b]) where baseline = exp(a + b * roughness).
    """
    ok = warm & np.isfinite(cpr) & (cpr > 0) & np.isfinite(roughness)
    x = roughness[ok].astype(np.float64)
    y = np.log(cpr[ok].astype(np.float64))
    edges = np.percentile(x, np.linspace(0, 100, 21))
    idx = np.digitize(x, edges[1:-1])
    xs = np.array([np.median(x[idx == i]) for i in range(20) if np.any(idx == i)])
    ys = np.array([np.median(y[idx == i]) for i in range(20) if np.any(idx == i)])
    b, a = np.polyfit(xs, ys, 1)
    excess = cpr - np.exp(a + b * roughness)
    ref = excess[ok]
    sigma = float(1.4826 * np.median(np.abs(ref - np.median(ref))) + 1e-9)
    return excess.astype(np.float32), sigma, np.array([a, b])


def classify(z_l: np.ndarray, z_s: np.ndarray,
             dop_l: Optional[np.ndarray] = None, dop_s: Optional[np.ndarray] = None) -> np.ndarray:
    """0 none, 1 near-surface (L+S), 2 deep (L only), 3 S only (inconsistent)."""
    det_l = z_l > DETECT_Z
    det_s = z_s > DETECT_Z
    if dop_l is not None:
        det_l &= np.nan_to_num(dop_l, nan=1.0) < DOP_ICE_MAX
    if dop_s is not None:
        det_s &= np.nan_to_num(dop_s, nan=1.0) < DOP_ICE_MAX
    cls = np.zeros(z_l.shape, dtype=np.uint8)
    cls[det_l & det_s] = 1
    cls[det_l & ~det_s] = 2
    cls[~det_l & det_s] = 3
    return cls


# --------------------------------------------------------------------------- #
# Depth inversion
# --------------------------------------------------------------------------- #

def _depth_from_ratio(e_l: np.ndarray, e_s: np.ndarray, log_k: float) -> np.ndarray:
    inv = 1.0 / DELTA_M["S"] - 1.0 / DELTA_M["L"]
    with np.errstate(divide="ignore", invalid="ignore"):
        d = (np.log(e_l) - np.log(e_s) - log_k) / inv
    d = np.where(e_s <= 0, D_MAX_M, d)          # S sees nothing -> deeper than S can see
    return np.clip(d, 0.0, D_MAX_M)


def calibrate_k(e_l: np.ndarray, e_s: np.ndarray, sig_l: float, sig_s: float,
                surface_stable: np.ndarray) -> Tuple[float, int]:
    """log(k) = median log(e_L / e_S) where surface ice is stable and both bands detect."""
    m = surface_stable & (e_l > DETECT_Z * sig_l) & (e_s > DETECT_Z * sig_s)
    n = int(m.sum())
    if n < MIN_CALIB_PX:
        return 0.0, n
    return float(np.median(np.log(e_l[m]) - np.log(e_s[m]))), n


def invert_depth(e_l: np.ndarray, e_s: np.ndarray, sig_l: float, sig_s: float,
                 log_k: float, n_samples: int = 32, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """Monte-Carlo depth-to-ice (m). Returns (mean, std); NaN where L-band has no ice signal."""
    rng = np.random.default_rng(seed)
    total = np.zeros(e_l.shape, np.float64)
    sq = np.zeros_like(total)
    cnt = np.zeros(e_l.shape, np.int32)
    for _ in range(n_samples):
        sl = e_l + rng.normal(0, sig_l, e_l.shape).astype(np.float32)
        ss = e_s + rng.normal(0, sig_s, e_s.shape).astype(np.float32)
        valid = sl > 0
        d = _depth_from_ratio(np.where(valid, sl, 1.0), ss, log_k)
        total += np.where(valid, d, 0.0)
        sq += np.where(valid, d * d, 0.0)
        cnt += valid
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / cnt
        std = np.sqrt(np.maximum(sq / cnt - mean ** 2, 0.0))
    detected = e_l > DETECT_Z * sig_l
    mean = np.where(detected, mean, np.nan)
    std = np.where(detected, std, np.nan)
    return mean.astype(np.float32), std.astype(np.float32)


def dual_band_depth(cpr_l: np.ndarray, cpr_s: np.ndarray, roughness: np.ndarray,
                    tmax: np.ndarray, dop_l: Optional[np.ndarray] = None,
                    dop_s: Optional[np.ndarray] = None, n_samples: int = 32) -> Dict:
    """Full L/S pipeline -> dict with depth, depth_std, class, z-scores and calibration info."""
    warm = tmax > 150.0
    e_l, sig_l, fit_l = cpr_excess(cpr_l, roughness, warm)
    e_s, sig_s, fit_s = cpr_excess(cpr_s, roughness, warm)
    e_l, e_s = np.nan_to_num(e_l), np.nan_to_num(e_s)
    z_l, z_s = e_l / sig_l, e_s / sig_s
    cls = classify(z_l, z_s, dop_l, dop_s)
    cls[~(np.isfinite(cpr_l) & np.isfinite(cpr_s) & np.isfinite(roughness))] = NO_DATA
    log_k, n_cal = calibrate_k(e_l, e_s, sig_l, sig_s, tmax < CALIB_TMAX_K)
    depth, depth_std = invert_depth(e_l, e_s, sig_l, sig_s, log_k, n_samples)
    depth = np.where((cls == 3) | (cls == NO_DATA), np.nan, depth)
    depth_std = np.where(np.isfinite(depth), depth_std, np.nan)
    # Enrichment test: warm pixels give the false-positive rate. A class only
    # carries information if its rate in cold pixels is clearly above that.
    valid = cls != NO_DATA
    cold = valid & (tmax < 110.0)
    warm_v = valid & warm
    enrichment = {}
    for c in (1, 2, 3):
        fp = float(np.mean(cls[warm_v] == c)) if warm_v.any() else float("nan")
        tp = float(np.mean(cls[cold] == c)) if cold.any() else float("nan")
        enrichment[CLASS_NAMES[c]] = {"rate_warm": fp, "rate_cold": tp, "ratio": tp / fp if fp > 0 else float("inf")}
    significant = enrichment[CLASS_NAMES[2]]["ratio"] > MIN_ENRICHMENT or enrichment[CLASS_NAMES[1]]["ratio"] > MIN_ENRICHMENT
    return {
        "depth_m": depth, "depth_std_m": depth_std, "class": cls,
        "z_l": z_l.astype(np.float32), "z_s": z_s.astype(np.float32),
        "info": {
            "sigma_L": sig_l, "sigma_S": sig_s, "log_k": log_k, "k": float(np.exp(log_k)),
            "n_calibration_px": n_cal, "k_calibrated": n_cal >= MIN_CALIB_PX,
            "baseline_fit_L": fit_l.tolist(), "baseline_fit_S": fit_s.tolist(),
            "delta_m": DELTA_M,
            "enrichment_cold_vs_warm": enrichment,
            "depth_signal_significant": bool(significant),
        },
    }
