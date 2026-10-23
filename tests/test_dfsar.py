"""Synthetic checks for dfsar.py. Run: python tests/test_dfsar.py  (or pytest tests)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dfsar  # noqa: E402


def test_full_pol_cpr_canonical_targets():
    one = np.ones((8, 8), complex)
    zero = np.zeros((8, 8), complex)
    # Flat surface / sphere: odd-bounce, same-sense power ~ 0.
    assert np.all(dfsar.full_pol_cpr(one, zero, one, looks=(1, 1)) < 1e-6)
    # Dihedral: even-bounce, CPR very large.
    assert np.all(dfsar.full_pol_cpr(one, zero, -one, looks=(1, 1)) > 1e6)


def test_compact_pol_unpolarised_noise():
    rng = np.random.default_rng(1)
    shape = (200, 200)
    e_h = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    e_v = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    cpr, dop = dfsar.compact_pol_cpr_dop(e_h, e_v, looks=(15, 15))
    assert abs(np.median(cpr) - 1.0) < 0.1
    assert np.median(dop) < 0.15


def test_compact_pol_fully_polarised():
    e_h = np.ones((20, 20), complex)
    e_v = 1j * np.ones((20, 20), complex)
    _, dop = dfsar.compact_pol_cpr_dop(e_h, e_v, looks=(3, 3))
    assert np.allclose(dop, 1.0, atol=1e-6)


def _synthetic_scene(seed=0, n=300):
    """Left third warm & ice-free, middle cold & surface ice (D=0), right cold with buried ice."""
    rng = np.random.default_rng(seed)
    rough = rng.uniform(2, 25, (n, n)).astype(np.float32)
    tmax = np.full((n, n), 250.0, np.float32)
    tmax[:, n // 3:] = 80.0
    true_d = np.full((n, n), np.nan, np.float32)
    true_d[:, n // 3: 2 * n // 3] = 0.0
    true_d[:, 2 * n // 3:] = np.linspace(0.2, 2.0, n)[:, None]
    base = np.exp(-0.9 + 0.015 * rough)
    amp, k = 0.6, {"L": 1.3, "S": 1.0}
    cpr = {}
    for b in "LS":
        ice = np.where(np.isfinite(true_d), amp * k[b] * np.exp(-np.nan_to_num(true_d) / dfsar.DELTA_M[b]), 0)
        cpr[b] = (base + ice + rng.normal(0, 0.02, (n, n))).astype(np.float32)
    return rough, tmax, true_d, cpr


def test_dual_band_depth_recovers_truth():
    rough, tmax, true_d, cpr = _synthetic_scene()
    out = dfsar.dual_band_depth(cpr["L"], cpr["S"], rough, tmax, n_samples=16)
    info = out["info"]
    assert info["k_calibrated"]
    assert abs(info["k"] - 1.3) < 0.1, info["k"]

    n = rough.shape[0]
    warm = np.s_[:, : n // 3]
    surf = np.s_[:, n // 3: 2 * n // 3]
    assert (out["class"][warm] > 0).mean() < 0.02
    assert (out["class"][surf] == 1).mean() > 0.95
    assert np.nanmedian(out["depth_m"][surf]) < 0.1
    # Buried ice still seen by S-band (true depth 0.2 .. ~1.0 m): recovered within 0.2 m.
    rows = slice(0, int(n * 0.45))
    err = np.abs(out["depth_m"][rows, 2 * n // 3:] - true_d[rows, 2 * n // 3:])
    assert np.nanmedian(err) < 0.2, np.nanmedian(err)
    # Deepest ice: L-only and reported deeper than 1 m.
    assert (out["class"][-20:, 2 * n // 3:] == 2).mean() > 0.8
    assert np.nanmedian(out["depth_m"][-20:, 2 * n // 3:]) > 1.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
