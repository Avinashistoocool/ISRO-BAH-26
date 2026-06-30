import numpy as np

# -----------------------------
# utility normalization
# -----------------------------
def normalize(x):
    x = np.nan_to_num(x)
    return (x - x.min()) / (x.max() - x.min() + 1e-8)


# -----------------------------
# main probabilistic model
# -----------------------------
def ice_probability_map(
    cpr_L,
    cpr_S,
    dop_L,
    dop_S,
    slope,
    roughness,
    psr_mask
):

    # =============================
    # 1. RADAR LAYER
    # =============================

    cpr_mean = (cpr_L + cpr_S) / 2.0
    dop_mean = (dop_L + dop_S) / 2.0

    radar_score = (
        0.6 * (cpr_mean > 1.0).astype(float) +
        0.4 * (1.0 - normalize(dop_mean))
    )

    # =============================
    # 2. FREQUENCY STABILITY
    # =============================

    cpr_diff = np.abs(cpr_L - cpr_S)
    stability = 1.0 - normalize(cpr_diff)

    # =============================
    # 3. TERRAIN PRIOR
    # =============================

    slope_n = normalize(slope)
    rough_n = normalize(roughness)

    geom_prior = (
        0.6 * (1.0 - slope_n) +
        0.4 * (1.0 - rough_n)
    )

    # =============================
    # 4. PSR CONSTRAINT (HARD PRIOR)
    # =============================

    psr = psr_mask.astype(float)

    # =============================
    # 5. COMBINATION (BAYESIAN-STYLE FUSION)
    # =============================

    raw_score = (
        0.35 * radar_score +
        0.25 * stability +
        0.25 * geom_prior +
        0.15 * psr
    )

    # squash to probability space
    prob = 1.0 / (1.0 + np.exp(-8.0 * (raw_score - 0.5)))

    return np.clip(prob, 0.0, 1.0)

