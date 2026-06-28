import numpy as np
from pathlib import Path

PROCESSED = Path("data/processed")

slope     = np.load(PROCESSED / "slope.npy")
roughness = np.load(PROCESSED / "roughness.npy")

print("── SLOPE (degrees) ─────────────────────────────")
print(f"  min:    {slope.min():.4f}")
print(f"  max:    {slope.max():.4f}")
print(f"  mean:   {slope.mean():.4f}")
print(f"  p50:    {np.percentile(slope, 50):.4f}")
print(f"  p90:    {np.percentile(slope, 90):.4f}")
print(f"  p95:    {np.percentile(slope, 95):.4f}")
print(f"  p99:    {np.percentile(slope, 99):.4f}")

print("\n── ROUGHNESS (raw gradient magnitude) ──────────")
print(f"  min:    {roughness.min():.4f}")
print(f"  max:    {roughness.max():.4f}")
print(f"  mean:   {roughness.mean():.4f}")
print(f"  p50:    {np.percentile(roughness, 50):.4f}")
print(f"  p75:    {np.percentile(roughness, 75):.4f}")
print(f"  p90:    {np.percentile(roughness, 90):.4f}")
print(f"  p95:    {np.percentile(roughness, 95):.4f}")
print(f"  p99:    {np.percentile(roughness, 99):.4f}")

print("\n── WHAT THE COST MAP ASSUMED (wrong) ───────────")
print(f"  normalise(roughness, 0, 700)")
print(f"  Your actual max: {roughness.max():.1f}")
print(f"  → Every cell was capped at {min(roughness.max()/700, 1)*100:.1f}% of the scale")
print(f"  → Mean cell normalised to: {min(roughness.mean()/700, 1):.4f} (near zero = all green)")

print("\n── OBSTACLE CUTOFF PREVIEW ─────────────────────")
for pct in [70, 75, 80, 85, 90, 95]:
    thresh = np.percentile(roughness, pct)
    excluded = 100 * (roughness > thresh).mean()
    print(f"  p{pct} threshold ({thresh:.1f}) → {excluded:.1f}% cells excluded")

print("\n── SLOPE CUTOFF PREVIEW ────────────────────────")
for deg in [5, 10, 15, 20, 25, 30]:
    excluded = 100 * (slope > deg).mean()
    print(f"  slope > {deg:2d}° → {excluded:.1f}% cells excluded")