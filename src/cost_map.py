import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from pathlib import Path

ROOT      = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
OUTPUTS   = ROOT / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)

# ── WEIGHTS ──────────────────────────────────────────────────────────
WEIGHTS = {
    'slope':        0.55,   # was 0.35 — absorbs illumination share
    'roughness':    0.45,   # was 0.25 — absorbs ice share
    # illumination and ice set to 0 until real data arrives
}

# ── THRESHOLDS (derived from diagnostic output) ───────────────────
SLOPE_HARD_LIMIT     = 10.0    # °      → excludes 18.2% of cells
ROUGHNESS_HARD_LIMIT = 232.3   # LEV    → excludes 15.0% of cells
OBSTACLE_COST        = 1e6

# ── NORMALISATION BOUNDS (p1 → p99) ──────────────────────────────
SLOPE_NORM_MAX = 24.2           # p99 of slope
ROUGH_NORM_MAX = 532.9          # p99 of roughness

# ── LOAD ─────────────────────────────────────────────────────────────
print("Loading terrain arrays...")
slope     = np.load(PROCESSED / "slope.npy")
roughness = np.load(PROCESSED / "roughness.npy")
Theta     = np.load(PROCESSED / "Theta.npy")
R         = np.load(PROCESSED / "R.npy")

print(f"Grid shape: {slope.shape}")

# ── NORMALISE ────────────────────────────────────────────────────────
slope_norm     = np.clip(slope     / SLOPE_NORM_MAX, -1, 1)
roughness_norm = np.clip(roughness / ROUGH_NORM_MAX, -1, 1)

# Placeholders — swap in real rasters when available

# Placeholders — SET TO ZERO, not 0.5
illumination_penalty = np.zeros_like(slope)
ice_penalty          = np.zeros_like(slope)

# ── HARD EXCLUSION MASK ───────────────────────────────────────────
obstacle_mask = (slope > SLOPE_HARD_LIMIT) | (roughness > ROUGHNESS_HARD_LIMIT)

print(f"\nObstacle breakdown:")
print(f"  Slope    > {SLOPE_HARD_LIMIT}°   : "
      f"{100*(slope > SLOPE_HARD_LIMIT).mean():.1f}% cells")
print(f"  Roughness > {ROUGHNESS_HARD_LIMIT} : "
      f"{100*(roughness > ROUGHNESS_HARD_LIMIT).mean():.1f}% cells")
print(f"  Combined excluded : {100*obstacle_mask.mean():.1f}% cells")
print(f"  Traversable       : {100*(~obstacle_mask).mean():.1f}% cells")

# ── WEIGHTED COST ─────────────────────────────────────────────────
cost = (WEIGHTS['slope']        * slope_norm
      + WEIGHTS['roughness']    * roughness_norm
        )

# Apply obstacles
cost[obstacle_mask] = OBSTACLE_COST
cost = np.nan_to_num(cost, nan=OBSTACLE_COST)

# Traversable cost stats
traversable = cost[~obstacle_mask]
print(f"\nTraversable cost distribution:")
print(f"  min:    {traversable.min():.4f}")
print(f"  mean:   {traversable.mean():.4f}")
print(f"  median: {np.median(traversable):.4f}")
print(f"  max:    {traversable.max():.4f}")

# ── SAVE ─────────────────────────────────────────────────────────
np.save(OUTPUTS / "cost_map.npy", cost)
np.save(OUTPUTS / "obstacle_mask.npy", obstacle_mask)
print(f"\nSaved → outputs/cost_map.npy")
print(f"Saved → outputs/obstacle_mask.npy")

# ── VISUALISE ────────────────────────────────────────────────────
faustini_theta = np.radians(180.0 + 77.0)
faustini_r     = 81.8

fig, axes = plt.subplots(1, 3, figsize=(22, 7),
                         subplot_kw=dict(projection='polar'))

# ── Panel 1: Cost map (traversable cells only) ──
ax = axes[0]
cost_viz = np.where(obstacle_mask, np.nan, cost)
mesh = ax.pcolormesh(Theta, R, cost_viz,
                     cmap='RdYlGn_r', shading='auto', vmin=0, vmax=1)
ax.set_theta_zero_location('S')
ax.grid(color='white', alpha=0.15)
fig.colorbar(mesh, ax=ax, label='Traversal Cost  (0 = easy · 1 = hard)',
             orientation='horizontal', pad=0.06)
ax.set_title("Cost Map", pad=16, fontsize=13, fontweight='bold')
ax.plot(faustini_theta, faustini_r, 'c*', markersize=14, label='Faustini')
ax.legend(loc='lower right', fontsize=9)

# ── Panel 2: Obstacle mask ──
ax2 = axes[1]
obs_rgb = np.where(obstacle_mask[:,:,np.newaxis],
                   [0.85, 0.1, 0.2],    # red  = excluded
                   [0.1,  0.5, 0.15])   # green = traversable
ax2.pcolormesh(Theta, R, obstacle_mask.astype(float),
               cmap='RdYlGn_r', shading='auto', vmin=0, vmax=1)
ax2.set_theta_zero_location('S')
ax2.grid(color='white', alpha=0.15)
ax2.set_title(f"Obstacle Mask\n"
              f"slope>{SLOPE_HARD_LIMIT}° OR roughness>{ROUGHNESS_HARD_LIMIT:.0f}  "
              f"→  {100*obstacle_mask.mean():.1f}% excluded",
              pad=16, fontsize=11, fontweight='bold')
ax2.plot(faustini_theta, faustini_r, 'c*', markersize=14)

# ── Panel 3: Slope contribution only (most physically meaningful) ──
ax3 = axes[2]
mesh3 = ax3.pcolormesh(Theta, R,
                        np.where(obstacle_mask, np.nan, slope_norm),
                        cmap='magma', shading='auto', vmin=0, vmax=1)
ax3.set_theta_zero_location('S')
ax3.grid(color='white', alpha=0.15)
fig.colorbar(mesh3, ax=ax3, label='Normalised Slope  (0–24.2°)',
             orientation='horizontal', pad=0.06)
ax3.set_title("Slope Component Only", pad=16, fontsize=13, fontweight='bold')
ax3.plot(faustini_theta, faustini_r, 'c*', markersize=14)

plt.suptitle("Faustini PSR — Traversal Cost Map  "
             f"(slope w={WEIGHTS['slope']}  "
             f"roughness w={WEIGHTS['roughness']})",
             fontsize=14, fontweight='bold', y=1.01)
plt.tight_layout()

out_fig = OUTPUTS / "cost_map.png"
plt.savefig(out_fig, dpi=200, bbox_inches='tight')
print(f"Saved → {out_fig}")
plt.show()
