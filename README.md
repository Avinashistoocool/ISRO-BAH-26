# ISRO-BAH-26-
This project maps subsurface lunar ice using Chandrayaan-2 DFSAR radar polarimetry. It identifies safe landing zones near doubly shadowed craters and computes an optimal, power-constrained rover traverse to access these ancient volatile deposits.
# ISRO’s BAH’26

Start date: 03/24/2025
End date: 07/01/2026
Start value: 0
End value: 100
Progress: 0%
Priority: High
Team: Account Management
Status: In progress

### About project

# Lunar PSR Rover Path Planning

### Chandrayaan-2 DFSAR Ice Detection & Optimal Traverse Design

A hackathon project for the **ISRO Chandrayaan-2 Lunar South Polar Exploration Challenge**.

Detects subsurface ice in permanently shadowed regions (PSRs) and computes a safe, energy-efficient rover traverse path from landing site to target crater.

---

## Problem Statement

The lunar South Pole hosts **doubly shadowed craters** — craters within PSRs — where temperatures drop to −230 °C and water ice may have accumulated over billions of years. Identifying these ice deposits and designing a rover path to access them is a core challenge for future ISRO lunar missions.

This project:

1. Maps subsurface ice using Chandrayaan-2 DFSAR radar polarimetry
2. Selects a safe landing site near the doubly shadowed crater
3. Computes an optimal rover traverse path with terrain and power constraints

---

## Repository Structure

```
lunar-psr-rover/
├── data/
│   ├── raw/                    # Original DFSAR, DEM, OHRC datasets (not committed)
│   └── processed/              # Reprojected and co-registered rasters
│
├── notebooks/
│   ├── 01_preprocessing.ipynb  # CRS alignment, slope/roughness computation
│   ├── 02_ice_detection.ipynb  # CPR, DOP computation and ice mask
│   ├── 03_landing_site.ipynb   # Safety scoring and site selection
│   └── 04_path_planning.ipynb  # Cost map, A*, RRT*, metrics
│
├── src/
│   ├── preprocess.py           # Raster reprojection and terrain derivatives
│   ├── ice_detection.py        # CPR/DOP from DFSAR Stokes parameters
│   ├── landing_site.py         # Candidate site scoring
│   ├── cost_map.py             # Weighted traversability raster
│   ├── path_planner.py         # A* / D* Lite / RRT* implementations
│   └── metrics.py              # Path evaluation utilities
│
├── outputs/
│   ├── ice_probability_map.tif # Ice detection output raster
│   ├── landing_sites.geojson   # Ranked candidate landing sites
│   ├── rover_path.geojson      # Final optimized traverse path
│   └── figures/                # Publication-quality maps and charts
│
├── requirements.txt
└── README.md
```

---

## Datasets

| Dataset | Source | Purpose |
| --- | --- | --- |
| Chandrayaan-2 DFSAR | Provided by organizers | Radar ice detection (CPR, DOP) |
| LOLA DEM (LRO) | NASA PDS | Elevation, slope, roughness |
| Chandrayaan-2 OHRC | ISRO PRADAN | High-res surface imagery |
| ShadowCam (KPLO) | NASA/KARI | PSR floor imaging |
| LRO Diviner thermal | NASA PDS | Temperature / illumination maps |
| LRO LROC NAC | NASA PDS | Boulder distribution, surface texture |

> Download instructions for public datasets: see `data/README.md`
> 

---

## Methodology

### 1. Preprocessing

All datasets are reprojected to **Lunar South Polar Stereographic** and co-registered spatially.

Terrain derivatives are computed from the LOLA DEM:

```python
import richdem as rd

dem = rd.LoadGDAL("data/processed/lola_dem.tif")
slope     = rd.TerrainAttribute(dem, attrib='slope_degrees')
roughness = rd.TerrainAttribute(dem, attrib='roughness')
```

### 2. Ice Detection

Radar polarimetric parameters are computed from DFSAR Stokes matrix data.

**Circular Polarization Ratio (CPR)**

```
CPR = σ_same-sense / σ_opposite-sense
```

**Degree of Polarization (DOP)**

```
DOP = sqrt(Q² + U² + V²) / I
```

**Ice detection thresholds:**

```python
ice_mask = (cpr > 1.0) & (dop < 0.13)
```

Values above CPR 1.0 and below DOP 0.13 indicate volume scattering consistent with subsurface ice, as distinct from surface roughness effects.

### 3. Landing Site Selection

Candidate landing sites are scored on three criteria:

```python
score = (illumination_fraction * 0.4) \
      + (1 - normalized_distance_to_target * 0.35) \
      + (terrain_safety * 0.25)
```

Safety mask thresholds:

| Parameter | Safe threshold |
| --- | --- |
| Slope | < 5° |
| Roughness | < 0.3 m RMS |
| Illumination | > 70% of lunar day |
| Distance to PSR rim | < 5 km |

### 4. Path Planning

The terrain is modeled as a **weighted grid graph** over the DEM raster.

**Cost function per cell:**

```python
cost = (w1 * slope_cost
      + w2 * roughness_cost
      + w3 * illumination_penalty
      + w4 * (1 - ice_probability)
      + w5 * distance_cost)

# Default weights
w1, w2, w3, w4, w5 = 0.35, 0.25, 0.20, 0.15, 0.05
```

**Algorithms implemented:**

| Algorithm | Role |
| --- | --- |
| A* | Baseline — fast, optimal on grid |
| D* Lite | Dynamic replanning as new terrain is revealed |
| RRT* | Continuous-space, asymptotically optimal |
| DQN (optional) | Reinforcement learning agent for innovation |

**Rover physical constraints:**

```
Max traversable slope:   15°
Max step height:         0.3 m
Operational speed:       ~0.1 km/h
Battery range (PSR):     2–4 km per charge
Max daily traverse:      ~1 km (conservative)
```

### 5. Path Metrics

```python
metrics = {
    "total_path_length_km":    ...,
    "max_slope_deg":           ...,
    "mean_slope_deg":          ...,
    "time_in_shadow_hours":    ...,
    "ice_zones_visited":       ...,
    "energy_consumed_Wh":      ...,
    "safety_score_pct":        ...   # % of path below slope threshold
}
```

---

## Installation

```bash
git clone https://github.com/your-org/lunar-psr-rover.git
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
stable-baselines3   # optional — for RL agent
```

---

## Quick Start

```bash
# 1. Preprocess all datasets
python src/preprocess.py --input data/raw/ --output data/processed/

# 2. Compute ice detection map
python src/ice_detection.py --dfsar data/processed/dfsar.tif --output outputs/ice_probability_map.tif

# 3. Select landing site
python src/landing_site.py --dem data/processed/lola_dem.tif --ice outputs/ice_probability_map.tif

# 4. Run path planner
python src/path_planner.py --algorithm astar --start "landing_site_primary" --goal "doubly_shadowed_crater"

# 5. Evaluate and export metrics
python src/metrics.py --path outputs/rover_path.geojson
```

---

## Key Results

*(Fill in after analysis)*

- **Target crater:** Doubly shadowed crater within Faustini PSR, lunar South Pole
- **Identified ice zones:** — km² of high-confidence ice (CPR > 1.0, DOP < 0.13)
- **Selected landing site:** — (lat, lon), illumination fraction: —%
- **Optimal path length:** — km
- **Estimated ice volume (top 5 m):** — m³

---

## Tools & Technologies

| Category | Tools |
| --- | --- |
| GIS | QGIS, ArcGIS |
| Programming | Python 3.10+ (NumPy, SciPy, GDAL, rasterio) |
| Radar processing | MIDAS, custom Python |
| Terrain analysis | richdem, PDAL, DEM tools |
| Path planning | networkx, custom A*/RRT*, stable-baselines3 |
| Visualization | QGIS, matplotlib, plotly, PyVista |

---

## Team

| Name | Role |
| --- | --- |
| Avinash & Esha | Path planning & optimization |
| Subodh & Aditya | Radar data processing |
| Subodh & Aditya | GIS & terrain analysis |
| All of us | Visualization & documentation |

---

## References

- Chandrayaan-2 DFSAR instrument description — ISRO
- Spudis et al. (2013) — Evidence for water ice on the Moon
- LRO LOLA Science Team — Lunar topographic model
- D* Lite: Koenig & Likhachev (2002)
- RRT*: Karaman & Frazzoli (2011)
- Noda et al. — Illumination conditions at lunar poles

---

## License

IIT License — see `LICENSE` for details.

---

*Submitted for the ISRO Chandrayaan-2 Lunar South Polar Exploration Hackathon*

### Action items

## Lunar PSR Rover — Mission Task Tracker

---

#### Phase 1 — Data Acquisition & Preprocessing

`Hours 0–5`

- [ ]  Download Chandrayaan-2 DFSAR data
    - Provided by organizers — confirm file format (GeoTIFF / HDF5)
- [ ]  Download LOLA DEM (LRO)
    - NASA PDS — Lunar South Polar Stereographic projection
- [ ]  Download LROC NAC / ShadowCam imagery
    - High-res surface texture and PSR floor imaging
- [ ]  Download LRO Diviner thermal data
    - Temperature maps and illumination fraction per pixel
- [ ]  Reproject all datasets to common CRS
    - Lunar South Polar Stereographic (EPSG:104903 or similar)
- [ ]  Co-register OHRC + LOLA DEM spatially
    - Use ground control points or image matching
- [ ]  Compute slope, aspect & roughness from DEM
    - Use richdem or GDAL — output as raster layers
- [ ]  Generate illumination model
    - SPICE kernels or LRO Diviner thermal data for PSR boundary mapping

---

#### Phase 2 — Ice Detection Layer

`Hours 5–10`

- [ ]  Process DFSAR — compute CPR raster
    - CPR = σ_same / σ_opposite — use MIDAS or custom Python
- [ ]  Process DFSAR — compute DOP raster
    - DOP from Stokes parameters (Q, U, V, I)
- [ ]  Apply ice detection thresholds
    - CPR > 1.0 AND DOP < 0.13 → high-confidence ice zone
- [ ]  Generate ice probability raster
    - Combine CPR + DOP into a probabilistic output layer
- [ ]  Identify doubly shadowed craters
    - Cross-check illumination model with OHRC imagery
- [ ]  Validate with LOLA CPR cross-reference
    - Sanity-check ice signatures against independent dataset

---

#### Phase 3 — Landing Site Selection

`Hours 10–15`

- [ ]  Build terrain safety mask
    - Slope < 5°, low roughness, no large boulders (from OHRC)
- [ ]  Build illumination mask
    - 70% of lunar day sunlit — confirms solar power viability
- [ ]  Buffer analysis around target crater
    - 5 km rover range constraint from landing ellipse
- [ ]  Score and rank candidate landing sites
    - Score = illumination × proximity × terrain safety
- [ ]  Select primary + 2 contingency sites
    - Document rationale for each selection

---

#### Phase 4 — Path Planning (Core Work)

`Hours 15–24`

- [ ]  Build weighted cost map
    - Combine slope, roughness, illumination, ice probability rasters
- [ ]  Tune cost function weights
    - w1 = 0.35 slope · w2 = 0.25 roughness · w3 = 0.20 illumination · w4 = 0.15 ice · w5 = 0.05 distance
- [ ]  Implement A* baseline planner
    - Grid-based graph with custom heuristic — validate output path
- [ ]  Implement D* Lite for dynamic replanning
    - Handles terrain updates mid-traverse
- [ ]  Implement RRT* for continuous-space comparison
    - Asymptotically optimal, good for non-grid terrain
- [ ]  (Optional) RL agent — DQN or PPO
    - State: position + battery + illumination · Reward: ice − slope penalty − energy
- [ ]  Run sensitivity analysis on cost weights
    - Pareto front: safety vs scientific value vs energy consumption
- [ ]  Add waypoint charging stops on illuminated ridges
    - Plan battery top-up points before PSR dip segments
- [ ]  Compute final path metrics
    - Length (km) · max slope · shadow time · ice zones visited · energy (Wh)

---

#### Phase 5 — Visualization & Documentation

`Hours 24–30`

- [ ]  Overlay rover path on DEM hillshade in QGIS
    - Export publication-quality map with legend and scale bar
- [ ]  Animate rover traverse on 3D DEM
    - Python matplotlib / PyVista or MATLAB 3D surface plot
- [ ]  Plot CPR / DOP rasters with ice probability overlays
    - Show detection thresholds visually with color scale
- [ ]  Estimate subsurface ice volume
    - Radar backscatter + dielectric model for top 5 m of regolith
- [ ]  Write methodology documentation
    - Datasets used, algorithms, parameters, results summary
- [ ]  Prepare final presentation slides
    - Cover: ice map · landing site · rover path · metrics · innovation angle

## Path optimisation:

Think of the lunar surface as a giant chessboard.

```
□ □ □ □ □
□ □ □ □ □
□ □ □ □ □
□ □ □ □ □
```

Each square (cell) contains information:

```
Slope
Shadow
Ice probability
Terrain roughness
```

---

## Step 1: Convert the Moon into a Grid

From the DEM:

```
Cell (1,1)
Slope = 5°

Cell (1,2)
Slope = 30°
```

Now every location has properties.

---

## Step 2: Assign a Cost

The rover doesn't like:

- steep slopes
- dangerous terrain
- deep shadows (depending on mission goals)

So give every cell a cost.

Example:

| Terrain | Cost |
| --- | --- |
| Flat | 1 |
| Moderate slope | 5 |
| Steep slope | 20 |
| Unsafe | 1000 |

Now the map becomes:

```
1   1   1   1
1  20  20   1
1   1   1   1
```

The rover will naturally try to avoid expensive cells.

---

## Step 3: Choose Start and Goal

Example:

```
Landing Site
      ↓
(5,5)

Ice Deposit
      ↓
(40,60)
```

Now you need the best route.

---

## Step 4: Use A*

For a hackathon, I strongly recommend **A***.

Why?

- Easy to implement
- Fast
- Well-known
- Judges recognize it

Conceptually:

```
Current Position
      ↓
Explore neighboring cells
      ↓
Estimate distance to goal
      ↓
Choose best option
```

It finds a path that's usually very close to optimal.

Python libraries exist, so you won't need to implement everything from scratch.

---

## Step 5: Make It Lunar-Specific

This is where your project becomes interesting.

Instead of:

```
Cost = Distance
```

use:

```
Cost =
Distance
+
Slope Penalty
+
Shadow Penalty
+
Hazard Penalty
```

For example:

```python
cost = (
    distance
    + 3*slope
    + 5*hazard
)
```

---

## Even Better

Suppose your rover wants to visit multiple ice sites.

Now you can use:

- A* between sites
- Traveling Salesman heuristics
- Multi-goal planning

But this is Version 2.

Don't start there.

---

## What I'd Build for the Hackathon

Version 1:

```
LOLA DEM
     ↓
Slope Map

Slope Map
     ↓
Cost Map

Landing Site
     ↓
A*

Ice Site
     ↓
Optimal Path
```

Output:

- Landing point
- Ice target
- Safe route

---

Use:

```
A*
+
Smart Cost Function
```

and spend the saved time improving your ice-detection and landing-site-selection pipeline. That's where the real novelty of your project lies.

### Documents

[https://app.notion.com](https://app.notion.com)
