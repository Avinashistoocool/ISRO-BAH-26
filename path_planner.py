"""
path_planner.py
================

Front-end script: loads config.json, asks cost_map.py (the backend) to
build the traversability grid, runs 8-connected A* from the rim to the
floor of Faustini crater, and displays the result interactively via
plt.show(). A PNG is also saved to config['output_png'] as a fallback for
headless runs.

Run:
    python path_planner.py
"""

from __future__ import annotations

import heapq
import itertools
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Import cost_map first (no matplotlib import there) so backend selection
# below is the first thing that touches matplotlib in this process.
import cost_map

import matplotlib

# Auto-switch to a real GUI backend if we're stuck on a non-interactive one
# (e.g. 'Agg', common in headless venvs). Without this, plt.show() silently
# does nothing. Never raises — falls back to Agg with a warning if no GUI
# toolkit is available, in which case the saved PNG is still your output.
_NON_INTERACTIVE_BACKENDS = {"agg", "cairo", "pdf", "pgf", "ps", "svg", "template"}
if matplotlib.get_backend().lower() in _NON_INTERACTIVE_BACKENDS:
    for _candidate in ("QtAgg", "Qt5Agg", "TkAgg", "MacOSX"):
        try:
            matplotlib.use(_candidate)
            break
        except Exception:
            continue

import matplotlib.pyplot as plt

RC = Tuple[int, int]
SQRT2 = math.sqrt(2.0)
_NEIGHBOURS: Tuple[Tuple[int, int, float], ...] = (
    (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
    (-1, -1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (1, 1, SQRT2),
)

CONFIG_PATH = "config.json"


# --------------------------------------------------------------------------- #
# A*
# --------------------------------------------------------------------------- #

def _octile(a: RC, b: RC, min_cost: float) -> float:
    dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
    dd = min(dr, dc)
    return min_cost * (dr + dc - 2 * dd + SQRT2 * dd)


def a_star(cost_grid: np.ndarray, start: RC, goal: RC) -> Optional[List[RC]]:
    """8-connected A* over a 2D cost grid (inf = impassable)."""
    n_rows, n_cols = cost_grid.shape
    for name, rc in (("start", start), ("goal", goal)):
        r, c = rc
        if not (0 <= r < n_rows and 0 <= c < n_cols):
            raise ValueError(f"{name}={rc} out of bounds for {cost_grid.shape}")
        if not np.isfinite(cost_grid[r, c]):
            raise ValueError(f"{name}={rc} is on an impassable cell")

    finite = cost_grid[np.isfinite(cost_grid)]
    min_cost = max(float(np.min(finite[finite > 0])) if np.any(finite > 0) else 1e-6, 1e-9)

    counter = itertools.count()
    open_heap: List[Tuple[float, int, RC]] = [(_octile(start, goal, min_cost), next(counter), start)]
    g_score: Dict[RC, float] = {start: 0.0}
    came_from: Dict[RC, RC] = {}
    closed: set = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1]
        closed.add(current)

        cr, cc = current
        for dr, dc, mult in _NEIGHBOURS:
            nr, nc = cr + dr, cc + dc
            if not (0 <= nr < n_rows and 0 <= nc < n_cols):
                continue
            ncost = cost_grid[nr, nc]
            if not np.isfinite(ncost):
                continue
            neighbour = (nr, nc)
            if neighbour in closed:
                continue
            tentative_g = g_score[current] + ncost * mult
            if tentative_g < g_score.get(neighbour, math.inf):
                g_score[neighbour] = tentative_g
                came_from[neighbour] = current
                f = tentative_g + _octile(neighbour, goal, min_cost)
                heapq.heappush(open_heap, (f, next(counter), neighbour))

    return None


def path_length_km(path: List[RC], pixel_size_m: float) -> float:
    length_px = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path[:-1], path[1:]))
    return length_px * pixel_size_m / 1000.0


def slope_stats_along_path(path: List[RC], slope_deg: np.ndarray) -> Tuple[float, float]:
    """Max and mean terrain slope (degrees) actually crossed by the path.

    This is a measured property of the resulting route, distinct from
    config['max_slope_deg'], which is only the *threshold* used to mark
    cells impassable when building the cost map. A path can legally use
    any slope up to that threshold; this tells you what it actually used.

    Args:
        path: List of (row, col) path pixels.
        slope_deg: Slope raster in degrees, same shape as the cost map.

    Returns:
        (max_slope_deg_on_path, mean_slope_deg_on_path). Returns (0.0, 0.0)
        for an empty path.
    """
    if not path:
        return 0.0, 0.0
    slopes = np.array([slope_deg[r, c] for r, c in path], dtype=np.float64)
    return float(np.max(slopes)), float(np.mean(slopes))


# --------------------------------------------------------------------------- #
# Visualisation — interactive via plt.show(), also saved as a fallback
# --------------------------------------------------------------------------- #

def plot_path(
    elevation: np.ndarray,
    cost_grid: np.ndarray,
    path: List[RC],
    start: RC,
    goal: RC,
    start_label: str,
    goal_label: str,
    out_path: Path,
    max_slope_on_path: float = 0.0,
    mean_slope_on_path: float = 0.0,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 8), dpi=150)
    ax.imshow(elevation, cmap="gray")
    ax.imshow(np.ma.masked_invalid(cost_grid), cmap="plasma", alpha=0.4)
    center_y, center_x = elevation.shape[0] / 2, elevation.shape[1] / 2
    view_size = 1000  # Adjust this size to zoom in/out as needed

    ax.set_xlim(center_x - view_size / 2, center_x + view_size / 2)
    ax.set_ylim(center_y + view_size / 2, center_y - view_size / 2)
    if path:
        arr = np.array(path)
        ax.plot(arr[:, 1], arr[:, 0], color="cyan", linewidth=2.5, label="A* path")

    ax.scatter([start[1]], [start[0]], marker="*", s=220, color="lime",
               edgecolor="black", linewidth=1.0, zorder=10, label=start_label)
    ax.scatter([goal[1]], [goal[0]], marker="D", s=110, color="red",
               edgecolor="black", linewidth=1.0, zorder=10, label=goal_label)

    ax.legend(loc="lower right", framealpha=0.85)
    title = "Faustini Crater \u2014 A* Path"
    if path:
        title += f"  (max slope {max_slope_on_path:.1f}\u00b0, mean {mean_slope_on_path:.1f}\u00b0)"
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Column (pixel)")
    ax.set_ylabel("Row (pixel)")
    fig.tight_layout()

    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved image: {out_path.resolve()}")

    plt.show()
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    config = cost_map.load_config(CONFIG_PATH)
    # Use the new center coordinate for clipping
    center_lat = config['center']['lat']
    center_lon = config['center']['lon']

    print(f"Clipping DEM around center ({center_lat}, {center_lon}), "
          f"radius {config['radius_m'] / 1000:.0f} km...")
    backend_result = cost_map.get_cost_map(config)  # backend does all the heavy lifting

    elevation = backend_result["elevation"]
    cost_grid = backend_result["cost_map"]
    slope_deg = backend_result["slope_deg"]
    meta = backend_result["meta"]
    start_rc = backend_result["start_rc"]
    goal_rc = backend_result["goal_rc"]

    print(f"start_rc={start_rc}  goal_rc={goal_rc}  crop shape={meta['shape']}")

    path = a_star(cost_grid, start_rc, goal_rc)
    max_slope_on_path, mean_slope_on_path = 0.0, 0.0
    if path is None:
        print("No path found. Try raising 'max_slope_deg' or 'radius_m' in config.json.")
        path = []
    else:
        max_slope_on_path, mean_slope_on_path = slope_stats_along_path(path, slope_deg)
        print(f"Path found: {len(path)} waypoints, {path_length_km(path, meta['pixel_size_m']):.2f} km")
        print(f"Slope along path: max={max_slope_on_path:.1f}\u00b0  mean={mean_slope_on_path:.1f}\u00b0 "
              f"(config limit: {config['max_slope_deg']}\u00b0)")

    plot_path(
        elevation, cost_grid, path, start_rc, goal_rc,
        config["start"].get("label", "Start"), config["goal"].get("label", "Goal"),
        Path(config["output_png"]),
        max_slope_on_path, mean_slope_on_path,
    )


if __name__ == "__main__":
    main()