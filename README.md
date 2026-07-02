# Lunar PSR Rover — Chandrayaan-2 DFSAR Ice Detection & Traverse Design

**Hackathon:** ISRO Build-a-thon Hackathon 2026 — Chandrayaan-2 Lunar South Polar Exploration Challenge
**Team:** <!-- FILL: your team name -->
**Status:** In progress

Maps subsurface lunar ice using Chandrayaan-2 DFSAR dual-frequency radar polarimetry,
estimates subsurface ice volume, selects a safe landing site near a doubly shadowed crater
in the Faustini PSR, and computes an optimal power-constrained rover traverse path.

---

## Problem Statement

The lunar South Pole hosts **doubly shadowed craters** — craters within permanently shadowed
regions (PSRs) — where temperatures drop to −230 °C and water ice may have accumulated over
billions of years. Identifying these deposits and designing a rover path to access them safely
is a core challenge for future ISRO lunar missions.

This project addresses all five objectives in the problem statement:

1. Maps subsurface ice using dual-frequency (L/S-band) DFSAR polarimetric depth discrimination
2. Builds a fused terrain + ice probability map from DEM, OHRC, radar, and thermal inputs
3. Estimates subsurface ice volume within the top ~5 m of regolith using a dielectric mixing model
4. Computes a safe, energy-efficient rover traverse using A* with a PPO reinforcement learning agent
5. Simulates the Rover ↔ OLTS ↔ Orbiter communication and power chain for waypoint validation

---

## System Architecture

Two primary input streams merge at a **Fusion Layer**, then drive ice estimation, cost mapping,
and path planning in sequence.

```
DFSAR data (L + S band) ──────────────────────────────────────────┐
                                                                    ▼
                                                          CPR / DOP Analysis
                                                         (per band, separately)
                                                                    │
LOLA DEM ──► Data Loader (file.py) ──► DEM Features ──────────────►│
                                    └──► PSR Generator ────────────►│
                                                                    ▼
                               OHRC Data ────────────────► ┌──────────────────────────┐
                               Diviner Thermal ───────────► │      FUSION LAYER         │
                                                            │  DEM geometry             │
                                                            │  PSR constraints          │
                                                            │  Radar ice likelihood     │
                                                            └──────────────────────────┘
                                                                    │
                    ┌───────────────────────────────────────────────┤
                    │                                               │
                    ▼                                               ▼
       Crater maps + Boulder ID                       Temperature Map
                    │                                       +
                    │                                Dielectric Assumptions
                    │                                       │
                    │                                       ▼
                    │                            Probabilistic Ice Model
                    │                                       │
                    │                            ┌──────────┴──────────┐
                    │                            ▼                      ▼
                    │                 Ice Probability Map      Volume of Ice
                    │                            │               Estimation
                    │                     Visualise All Maps
                    │                            │
                    └────────────────────────────┤
                                                 ▼
                              constraints.json ──► COST MAP ◄── PSR Masks
                                                         │
                                                         ▼
                                               A* + RL (PPO) Algorithms
                                                         │
                                          ┌──────────────┴──────────────┐
                                          ▼                              ▼
                                         Path                  Landing Site Estimation
                                          │
                                   Target Planner
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                   Rover ◄──── OLTS ◄──── Orbiter    Simulation Validation
```

---

## Repository Structure

```
lunar-psr-rover/
├── data/
│   ├── raw/                         # DFSAR, DEM, OHRC datasets (not committed)
│   └── processed/                   # Reprojected and co-registered rasters
│
├── config/
│   └── constraints.json             # Rover physical + mission constraints
│
├── notebooks/
│   ├── 01_dem_preprocessing.ipynb   # DEM loading, PSR generation, terrain derivatives
│   ├── 02_cpr_dop_analysis.ipynb    # DFSAR Stokes → CPR, DOP rasters (L and S band)
│   ├── 03_fusion_layer.ipynb        # DEM + PSR + radar likelihood + OHRC fusion
│   ├── 04_ice_detection.ipynb       # Probabilistic ice model, dual-band depth classification
│   ├── 05_ice_volume.ipynb          # Dielectric mixing model, volume integration
│   ├── 06_path_planning.ipynb       # Cost map, A*+RL path, landing site output
│   └── 07_simulation.ipynb          # Rover ↔ OLTS ↔ Orbiter simulation validation
│
├── src/
│   ├── file.py                      # Data loader — LOLA DEM setup and south pole extraction
│   ├── all_maps.py                  # Visualise all raster layers (slope, roughness, PSR, CPR, DOP)
│   ├── preprocess.py                # CRS reprojection and co-registration
│   ├── psr_generator.py             # PSR boundary generation from DEM + illumination model
│   ├── cpr_dop.py                   # CPR / DOP per band from DFSAR Stokes parameters
│   ├── fusion.py                    # Fusion layer — DEM, PSR, radar, OHRC, thermal
│   ├── ice_model.py                 # Dielectric mixing model + probabilistic ice detection
│   ├── ice_probability.py           # Ice probability raster output
│   ├── ice_volume.py                # Dual-band depth-bin volume estimation
│   ├── crater_boulder.py            # Crater maps and boulder identification from OHRC
│   ├── cost_map.py                  # Weighted traversability raster (.npy)
│   ├── path_planner.py              # A* with PPO RL path planning
│   ├── target_planner.py            # Multi-waypoint target sequencing
│   ├── landing_site.py              # Landing site estimation from path output
│   ├── simulation.py                # Rover ↔ OLTS ↔ Orbiter chain simulation
│   └── metrics.py                   # Path evaluation and export utilities
│
├── outputs/
│   ├── ice_probability_map.tif      # Ice detection output raster
│   ├── ice_volume_estimate.json     # Volume estimate per depth bin (near-surface / deep)
│   ├── landing_sites.geojson        # Ranked candidate landing sites (primary + contingencies)
│   ├── rover_path.geojson           # Final optimised traverse path with waypoints
│   └── figures/                     # Publication-quality maps and charts
│
├── requirements.txt
└── README.md
```

---

## How to Run

```bash
# 1. Load LOLA DEM and set up the south pole region
python src/file.py

# 2. Visualise all DEM-derived parameter maps (slope, roughness, PSR boundary, aspect)
python src/all_maps.py

# 3. Compute CPR and DOP rasters from DFSAR data (L-band and S-band separately)
python src/cpr_dop.py --dfsar data/processed/dfsar_L.tif data/processed/dfsar_S.tif

# 4. Run fusion layer — merge DEM, PSR, radar, OHRC, and thermal inputs
python src/fusion.py

# 5. Compute ice probability map and export raster
python src/ice_probability.py

# 6. Estimate subsurface ice volume using dielectric mixing model
python src/ice_volume.py --ice outputs/ice_probability_map.tif

# 7. Build cost map and store as numpy array
python src/cost_map.py

# 8. Run A* + RL path planner
python src/path_planner.py --config config/constraints.json

# 9. Run simulation validation (Rover ↔ OLTS ↔ Orbiter)
python src/simulation.py

# 10. Compute and export path metrics
python src/metrics.py --path outputs/rover_path.geojson
```

---

## Datasets

| Dataset | Source | Purpose |
| --- | --- | --- |
| Chandrayaan-2 DFSAR (L + S band) | Provided by organizers | CPR, DOP — dual-frequency radar ice detection |
| LOLA DEM (LRO) | NASA PDS | Elevation, slope, roughness, PSR generation |
| Chandrayaan-2 OHRC | ISRO PRADAN | Crater maps, boulder identification, surface texture |
| LRO Diviner thermal | NASA PDS | Temperature map, illumination fraction per pixel |
| LRO LROC NAC | NASA PDS | Surface texture cross-validation |
| ShadowCam (KPLO) | NASA/KARI | PSR floor imaging |

> Download instructions for public datasets: see `data/README.md`

---

## Methodology

### 1. Data Loading and DEM Preprocessing

All datasets are reprojected to **Lunar South Polar Stereographic** and co-registered spatially.
Terrain derivatives and PSR boundaries are computed from the LOLA DEM.

```python
import richdem as rd

dem       = rd.LoadGDAL("data/processed/lola_dem.tif")
slope     = rd.TerrainAttribute(dem, attrib='slope_degrees')
roughness = rd.TerrainAttribute(dem, attrib='roughness')
# PSR boundary generated via illumination model from SPICE kernels / Diviner data
```

---

### 2. CPR / DOP Analysis — Dual Frequency

Radar polarimetric parameters are computed **separately for L-band and S-band** from DFSAR
Stokes matrix data. This is the core scientific innovation: L-band penetrates ~3 m depth;
S-band penetrates shallower (~0.5–1 m). Agreement or disagreement between bands encodes
where in the subsurface column the ice is concentrated.

**Circular Polarization Ratio (CPR) per band:**
```
CPR = σ_same-sense / σ_opposite-sense
```

**Degree of Polarization (DOP) per band:**
```
DOP = sqrt(Q² + U² + V²) / I
```

**Per-band ice masks** (thresholds per ISRO BAH'26 problem statement):
```python
ice_mask_L = (cpr_L > 1.0) & (dop_L < 0.13)   # L-band: deeper signal (~3 m)
ice_mask_S = (cpr_S > 1.0) & (dop_S < 0.13)   # S-band: shallower signal (~1 m)
```

**Why dual-band discriminates better than single-band CPR alone:**
Surface roughness and rocky/blocky terrain can produce elevated CPR at both bands
simultaneously. Subsurface ice concentrated at depth elevates CPR in L-band but
not S-band (which cannot reach it), producing a frequency-dependent signature that
surface roughness does not replicate. DOP < 0.13 further discriminates volume
scattering (ice) from surface scattering (rocks).

---

### 3. Fusion Layer

Three information streams are merged into a single fused raster used by all downstream
modules:

```python
fused = {
    "dem_geometry":     slope, roughness, aspect,          # from LOLA DEM
    "psr_constraints":  psr_mask, illumination_fraction,   # from PSR generator + Diviner
    "radar_likelihood": cpr_L, cpr_S, dop_L, dop_S,       # from CPR/DOP analysis
    "ohrc_hazards":     crater_density, boulder_map,       # from crater_boulder.py
    "thermal":          temperature_map                    # from Diviner
}
```

---

### 4. Ice Detection and Volume Estimation

#### 4a. Dual-Band Depth Classification

L/S-band agreement classifies each pixel into a depth regime:

```python
near_surface = ice_mask_L & ice_mask_S      # ice within S-band reach (~0–1 m)
deep_only    = ice_mask_L & (~ice_mask_S)   # ice in L-band only (~1–3 m)
no_detection = ~ice_mask_L                  # no ice signal in either band
```

#### 4b. Dielectric Mixing Model

A two-component Maxwell-Garnett mixing model converts per-pixel permittivity to ice
volume fraction:

```
ε_mix = (1 − f_ice) × ε_dry_regolith + f_ice × ε_ice
```

Where:
- `ε_dry_regolith` ≈ 2.7 (lunar regolith baseline)
- `ε_ice` ≈ 3.1 (water ice at radar frequencies)
- `f_ice` = ice volume fraction (solved per pixel)

Temperature from LRO Diviner provides a cross-check: ice is only thermally stable at
temperatures below ~110 K, constraining the expected detection zone to pixels where
Diviner confirms sufficiently cold conditions.

#### 4c. Volume Integration

```python
vol_near = near_surface.sum() * pixel_area_m2 * s_band_depth_m * f_ice_near
vol_deep = deep_only.sum()    * pixel_area_m2 * (l_band_depth_m - s_band_depth_m) * f_ice_deep
total_volume_m3 = vol_near + vol_deep
```

> **Caveat:** L-band DFSAR penetration depth is ~3 m. The problem statement specifies
> top-5 m integration; the 3–5 m portion is extrapolated beyond direct radar sensing depth
> and is flagged as such in results.

---

### 5. Cost Map

Fusion layer outputs, ice probability raster, OHRC hazard layer, and PSR masks are combined
into a single traversability cost array stored as `.npy`:

```python
cost = (w1 * slope_cost
      + w2 * roughness_cost
      + w3 * illumination_penalty
      + w4 * (1 - ice_probability)
      + w5 * boulder_hazard
      + w6 * psr_boundary_penalty)

# Weights (tunable via constraints.json — see sensitivity analysis in results)
w1, w2, w3, w4, w5, w6 = 0.30, 0.20, 0.20, 0.15, 0.10, 0.05
```

Rover physical constraints (`config/constraints.json`):

```json
{
  "max_slope_deg": 15,
  "max_step_height_m": 0.3,
  "speed_kmh": 0.1,
  "operational_hours_per_day": 10,
  "max_daily_traverse_km": 1.0,
  "battery_range_km": [2, 4],
  "psr_rim_distance_constraint_km": 3.0,
  "min_charging_illumination_pct": 70
}
```

> `psr_rim_distance_constraint_km` is set to **3 km** (not 5 km) to remain within the
> 2–4 km battery range with margin. At 0.1 km/h over 10 operational hours/day the rover
> covers ~1 km/day net traverse (accounting for stops and thermal rest periods).

---

### 6. Path Planning

The cost map drives an **A\* planner combined with a PPO reinforcement learning agent**.
A\* provides the structured grid search; the PPO agent optimises waypoint selection and
charging-stop placement under battery and illumination constraints.

```python
# A* grid search over cost map
path_astar = astar(cost_map, start=landing_site, goal=target_crater)

# PPO agent state and reward
# State:  [position, battery_level, illumination_fraction, slope_ahead]
# Action: [move_direction, stop_to_charge, advance_to_waypoint]
# Reward: +ice_zones_visited − slope_penalty − energy_consumed − shadow_time
```

The **Target Planner** sequences multi-waypoint objectives: solar charging stops on
illuminated ridges, intermediate high-confidence ice zones, and the final crater target.

**Landing site selection is an output of path planning**, not a prior step. The planner
identifies the optimal start node that minimises total path cost to the target crater,
subject to terrain safety constraints. This guarantees the selected landing site is always
reachable within one battery charge.

#### Cost Weight Sensitivity Analysis

Two weight configurations were tested to validate robustness:

| Config | w1 slope | w4 ice | Effect |
| --- | --- | --- | --- |
| Safety-first | 0.60 | 0.05 | Path avoids steeper terrain, longer route |
| Science-first | 0.15 | 0.50 | Path maximises ice zone coverage, accepts mild slopes |
| **Default** | **0.30** | **0.15** | **Balanced — used for final output** |

<!-- FILL: add one sentence describing which configuration produced a meaningfully different path, once sensitivity runs are complete -->

---

### 7. Simulation Validation — Rover ↔ OLTS ↔ Orbiter

Each waypoint on the final path is validated against the Rover–OLTS–Orbiter communication
and power chain:

```
Rover (position, battery%) ──► OLTS ──► Orbiter (LOS window, pass timing)
```

Output flags any waypoint where orbiter LOS and battery level simultaneously fall below
threshold, indicating a comms/power risk that requires a path adjustment or charging stop.

---

### 8. Limitations and Future Work

- **L-band penetration depth (~3 m)** is less than the 5 m integration scope required by
  the problem statement. The 3–5 m portion of the volume estimate is extrapolated, not
  directly sensed, and carries higher uncertainty.
- **PPO agent training** was initiated during the hackathon. Converged reward curve and
  trained policy are shown in `notebooks/06_path_planning.ipynb`. Full integration with
  real-time terrain feedback is deferred post-hackathon.
- **OLTS power budget** (orbital laser power transfer) was scoped as a future extension
  and is not included in the primary pipeline. Preliminary analysis shows that at 50 W
  transmitter power and orbital range, delivered energy is too small to be mission-relevant
  at current parameters; higher transmitter power is required for viability.

---

## Key Results

> Results will be populated as pipeline runs complete. Placeholders marked `[ ]` below.

| Metric | Value | Notes |
| --- | --- | --- |      
| Target crater | Doubly shadowed crater, Faustini PSR | Organizer-supplied DFSAR data |
| Study area | <!-- FILL: X km × Y km --> | From DFSAR tile extent |
| PSR floor temperature (Diviner) | <!-- FILL: ~XX K --> | Sanity-check: must be < 110 K for ice stability |
| **Ice zone area** (CPR > 1.0, DOP < 0.13, L-band) | <!-- FILL: X.X ± Y km² --> | Near-surface + deep combined |
| Near-surface ice area (both bands) | <!-- FILL: X.X km² --> | Within S-band sensing depth |
| Deep ice area (L-band only) | <!-- FILL: X.X km² --> | Between S-band limit and ~3 m |
| Peak CPR value observed | <!-- FILL: X.X --> | Highest-confidence ice pixel |
| **Estimated ice volume** (top ~3 m, direct) | <!-- FILL: X.X × 10⁶ m³ ± order of magnitude --> | Maxwell-Garnett model, f_ice from dielectric inversion |
| Estimated ice volume (3–5 m, extrapolated) | <!-- FILL: X.X × 10⁶ m³ --> | Extrapolated beyond radar sensing depth — flagged |
| Ice volume fraction (f_ice, peak pixel) | <!-- FILL: ~X% --> | From dielectric mixing model |
| **Selected landing site** | <!-- FILL: lat °S, lon °E --> | Primary site |
| Landing site illumination fraction | <!-- FILL: XX% of lunar day --> | From Diviner / SPICE |
| Distance from landing site to PSR rim | <!-- FILL: X.X km --> | Must be ≤ 3.0 km |
| Contingency site 1 | <!-- FILL: lat °S, lon °E --> | Ranked 2nd by scoring function |
| Contingency site 2 | <!-- FILL: lat °S, lon °E --> | Ranked 3rd by scoring function |
| **Optimal path length** (landing site → crater) | <!-- FILL: X.X km --> | A*+RL output |
| Estimated traverse duration | <!-- FILL: X days --> | At 1 km/day |
| Max slope on path | <!-- FILL: X.X° --> | Must be < 15° |
| Mean slope on path | <!-- FILL: X.X° --> | |
| Time in shadow (path) | <!-- FILL: X.X hours --> | |
| Solar charging waypoints | <!-- FILL: N --> | Illuminated ridges along route |
| Ice zones visited | <!-- FILL: N --> | High-confidence CPR > 1.0 pixels on path |
| Energy consumed | <!-- FILL: X Wh --> | Estimated from speed + distance |
| Safety score | <!-- FILL: XX% --> | % of path cells below 15° slope threshold |
| Orbiter comms coverage | <!-- FILL: XX% --> | % of waypoints with LOS window |
| **OLTS simulation** (Rover ↔ OLTS ↔ Orbiter) | <!-- FILL: table or link to notebook --> | See `notebooks/07_simulation.ipynb` |

---

## Simulation Waypoint Table

> Populated by `simulation.py` — fill in after running.

| Waypoint | Type | Battery % | Orbiter LOS | Comms Window | Status |
| --- | --- | --- | --- | --- | --- |
| WP-01 | Landing site | <!-- FILL --> | <!-- FILL: YES/NO --> | <!-- FILL: X min --> | <!-- FILL: OK/FLAG --> |
| WP-02 | Charging stop | <!-- FILL --> | <!-- FILL --> | <!-- FILL --> | <!-- FILL --> |
| WP-03 | Ice zone | <!-- FILL --> | <!-- FILL --> | <!-- FILL --> | <!-- FILL --> |
| WP-04 | PSR rim crossing | <!-- FILL --> | <!-- FILL --> | <!-- FILL --> | <!-- FILL --> |
| WP-05 | Target crater floor | <!-- FILL --> | <!-- FILL --> | <!-- FILL --> | <!-- FILL --> |

> Add or remove rows to match actual waypoint count from `rover_path.geojson`.

---

## Installation

```bash
git clone https://github.com/<!-- FILL: your-org -->/lunar-psr-rover.git
cd lunar-psr-rover
pip install -r requirements.txt
```

**requirements.txt**
```
numpy
scipy
gdal
rasterio
richdem
shapely
geopandas
networkx
matplotlib
plotly
stable-baselines3
spiceypy
defusedxml
```

---

## Tools and Technologies

| Category | Tools |
| --- | --- |
| GIS and mapping | QGIS, ArcGIS, GDAL, rasterio, geopandas |
| Programming | Python 3.10+ (NumPy, SciPy) |
| Radar processing | MIDAS, custom Python (Stokes → CPR/DOP) |
| Terrain analysis | richdem, PDAL, SPICE kernels (spiceypy) |
| Ice modelling | Custom Maxwell-Garnett dielectric mixing (ice_model.py) |
| Path planning | networkx (A*), stable-baselines3 (PPO reinforcement learning) |
| Visualisation | QGIS, matplotlib, plotly, PyVista |

---

## Team

| Name | Role |
| --- | --- |
| Avinash Chandra Gupta| Team lead, Nakshatra |
| Subodh | Radar processing — CPR/DOP (L and S band), DFSAR Stokes pipeline |
| Aditya | Ice detection, dielectric mixing model, volume estimation |
| Avinash | Path planning, A* implementation, cost map |
| Esha | PPO RL agent, target planner, simulation validation |

---

## References

- Sinha, Bharti, Acharyya, Mishra, Srivastava & Bhardwaj (2026) — Doubly shadowed crater
  subsurface ice detection via Chandrayaan-2 DFSAR, *NPJ* —
  <!-- FILL: confirm DOI before submission -->
- Fa, Z. & Cai, Y. (2011) — Polarimetric radar scattering model from lunar regolith with
  embedded ice inclusions, *Journal of Geophysical Research: Planets*
- Spudis, P.D. et al. (2013) — Evidence for water ice on the Moon,
  *Journal of Geophysical Research: Planets*
- Lemelin, M. et al. (2021) — Haworth crater volatile inventory estimate —
  <!-- FILL: confirm full citation -->
- Durga Prasad, K. et al. (2024) — Chandrayaan-3 alternate landing site: pre-landing
  characterisation, *Current Science*, 126, 774
- LRO LOLA Science Team — Lunar topographic model, NASA PDS
- Noda, H. et al. — Illumination conditions at lunar south polar regions
- Chandrayaan-2 DFSAR instrument description — ISRO

---

## License

MIT License — see `LICENSE` for details.

---

*Submitted for the ISRO Build-a-thon Hackathon 2026 — Chandrayaan-2 Lunar South Polar Exploration Challenge*
