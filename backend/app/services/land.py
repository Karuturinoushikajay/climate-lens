"""Open-ocean check against a precomputed 0.1-degree land mask (built by scripts/build_land_mask.py).

A cell is "near land" if it lies within about 50 km of Natural Earth 1:10m land or minor islands,
so coastal cities and islands pass while open-ocean points are rejected.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

MASK_PATH = Path(__file__).resolve().parents[1] / "data" / "land_mask.npz"
OCEAN_MESSAGE = (
    "This point is in the open ocean (more than ~50 km from land). "
    "ERA5 over the sea describes marine conditions; choose a point on or near land."
)
OCEAN_BOX_MESSAGE = (
    "This box is entirely open ocean (more than ~50 km from land). "
    "ERA5 over the sea describes marine conditions; choose an area that includes land."
)


@lru_cache(maxsize=1)
def _mask() -> tuple[np.ndarray, float]:
    with np.load(MASK_PATH) as data:
        cols = int(data["cols"])
        mask = np.unpackbits(data["bits"], axis=1, count=cols).astype(bool)
        return mask, float(data["res"])


def _row(lat: float, res: float, rows: int) -> int:
    return min(max(int((lat + 90) / res), 0), rows - 1)


def _col(lon: float, res: float, cols: int) -> int:
    return min(max(int((lon + 180) / res), 0), cols - 1)


def near_land(lat: float, lon: float) -> bool:
    mask, res = _mask()
    rows, cols = mask.shape
    return bool(mask[_row(lat, res, rows), _col(lon, res, cols)])


def box_has_land(south: float, west: float, north: float, east: float) -> bool:
    mask, res = _mask()
    rows, cols = mask.shape
    r0, r1 = _row(south, res, rows), _row(north, res, rows)
    c0, c1 = _col(west, res, cols), _col(east, res, cols)
    return bool(mask[r0 : r1 + 1, c0 : c1 + 1].any())
