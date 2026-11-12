# ISRO-BAH-26-
This project uses Chandrayaan-2 DFSAR radar polarimetry to map subsurface lunar ice. It finds safe landing zones near doubly shadowed craters. It also calculates an optimal rover traverse to these ancient volatile deposits, within the power limits.

Start date: 03/15/2025
End date: 07/01/2026
Status: In progress

### About project

# Lunar PSR Rover Path Planning

### Chandrayaan-2 DFSAR Ice Detection & Optimal Traverse Design

A hackathon project for the **ISRO Chandrayaan-2 Lunar South Polar Exploration Challenge**.

The project finds subsurface ice in permanently shadowed regions (PSRs). It calculates a safe, energy-efficient rover traverse path from the landing site to the target crater.

---

## Problem Statement

The lunar South Pole has **doubly shadowed craters**. These are craters in PSRs. In these craters, temperatures decrease to −230 °C, and water ice can have collected over billions of years. Future ISRO lunar missions must find these ice deposits and design a rover path to them.

This project does these tasks:

1. It maps subsurface ice with Chandrayaan-2 DFSAR radar polarimetry.
2. It selects a safe landing site near the doubly shadowed crater.
3. It calculates an optimal rover traverse path within the terrain and power limits.

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

> For the download instructions of the public datasets, refer to `data/README.md`.
> 

---

## Methodology

### 1. Preprocessing

All datasets are reprojected to **Lunar South Polar Stereographic** and co-registered spatially.

The terrain derivatives come from the LOLA DEM:

```python
import richdem as rd

dem = rd.LoadGDAL("data/processed/lola_dem.tif")
slope     = rd.TerrainAttribute(dem, attrib='slope_degrees')
roughness = rd.TerrainAttribute(dem, attrib='roughness')
```

### 2. Ice Detection

The radar polarimetric parameters are calculated from the DFSAR Stokes matrix data.

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

Values above CPR 1.0 and below DOP 0.13 show volume scattering that agrees with subsurface ice. This signature is different from the effects of surface roughness.

### 3. Landing Site Selection

The tool gives a score to each candidate landing site with three criteria:

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

The model of the terrain is a **weighted grid graph** over the DEM raster.

**Cost function for each cell:**

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
| A* | Baseline — fast, optimal on a grid |
| D* Lite | Dynamic replanning when the rover sees new terrain |
| RRT* | Continuous-space, asymptotically optimal |
| DQN (optional) | Reinforcement learning agent, as an innovation |

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
    - The organizers supply the data — confirm the file format (GeoTIFF / HDF5)
- [ ]  Download LOLA DEM (LRO)
    - NASA PDS — Lunar South Polar Stereographic projection
- [ ]  Download LROC NAC / ShadowCam imagery
    - High-res surface texture and PSR floor imaging
- [ ]  Download LRO Diviner thermal data
    - Temperature maps and the illumination fraction of each pixel
- [ ]  Reproject all datasets to common CRS
    - Lunar South Polar Stereographic (EPSG:104903 or similar)
- [ ]  Co-register OHRC + LOLA DEM spatially
    - Use ground control points or image matches
- [ ]  Compute slope, aspect & roughness from DEM
    - Use richdem or GDAL — the output is raster layers
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
    - Compare the ice signatures with an independent dataset

---

#### Phase 3 — Landing Site Selection

`Hours 10–15`

- [ ]  Build terrain safety mask
    - Slope < 5°, low roughness, no large boulders (from OHRC)
- [ ]  Build illumination mask
    - Sunlight for 70% of the lunar day — this confirms that solar power is viable
- [ ]  Buffer analysis around target crater
    - 5 km rover range constraint from landing ellipse
- [ ]  Score and rank candidate landing sites
    - Score = illumination × proximity × terrain safety
- [ ]  Select primary + 2 contingency sites
    - Record the reason for each selection

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
    - Updates the path when the terrain data changes during the traverse
- [ ]  Implement RRT* for continuous-space comparison
    - Asymptotically optimal, applicable to terrain without a grid
- [ ]  (Optional) RL agent — DQN or PPO
    - State: position + battery + illumination · Reward: ice − slope penalty − energy
- [ ]  Run sensitivity analysis on cost weights
    - Pareto front: safety vs scientific value vs energy consumption
- [ ]  Add waypoint charging stops on illuminated ridges
    - Plan battery charge points before the segments that go into the PSR
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
    - Show the detection thresholds with a color scale
- [ ]  Estimate subsurface ice volume
    - Radar backscatter + dielectric model for top 5 m of regolith
- [ ]  Write methodology documentation
    - Datasets, algorithms, parameters, summary of the results
- [ ]  Prepare final presentation slides
    - Cover: ice map · landing site · rover path · metrics · innovation angle

## Path optimisation:

The model of the lunar surface is a large grid of cells, as on a chessboard.

```
□ □ □ □ □
□ □ □ □ □
□ □ □ □ □
□ □ □ □ □
```

Each square (cell) contains this data:

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

Now each location has properties.

---

## Step 2: Assign a Cost

The rover must avoid these conditions:

- steep slopes
- dangerous terrain
- deep shadows (this is a function of the mission objectives)

Thus, give each cell a cost.

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

The planner selects a path that avoids cells with a high cost.

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

Now find the best route.

---

## Step 4: Use A*

For a hackathon, we strongly recommend **A***, for these reasons:

- It is easy to implement.
- It is fast.
- It is well-known.
- The judges know it.

The concept:

```
Current Position
      ↓
Explore neighboring cells
      ↓
Estimate distance to goal
      ↓
Choose best option
```

It usually finds a path that is almost optimal.

Python libraries are available. Thus, you do not have to implement all of the algorithm yourself.

---

## Step 5: Make It Lunar-Specific

This step makes the project different from a general planner.

Do not use:

```
Cost = Distance
```

Use:

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

## Possible Extension

The rover can have to go to two or more ice sites.

For this case, you can use:

- A* between sites
- Traveling Salesman heuristics
- Multi-goal planning

But this is Version 2.

Do not start with this version.

---

## Recommended Build for the Hackathon

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

Use the time that this saves to improve the pipeline for ice detection and landing-site selection. The real novelty of the project is in that pipeline.

### Documents

[https://app.notion.com](https://app.notion.com)
