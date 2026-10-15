"""Build backend/app/data/land_mask.npz from Natural Earth 1:10m land and minor islands.

Development tool only (needs shapely, which the API does not install). Usage:

    python scripts/build_land_mask.py ne_10m_land.geojson ne_10m_minor_islands.geojson

The GeoJSON files are from https://github.com/nvkelso/natural-earth-vector (public domain).
The output is a global 0.1-degree grid where a cell is True if it lies within about
DILATE_KM of land, so coastal points pass and only open-ocean points are rejected.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape

RES = 0.1
ROWS, COLS = 1800, 3600
DILATE_KM = 50.0
KM_PER_DEG = 111.2
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "land_mask.npz"


def load_geoms(paths: list[str]) -> list:
    geoms = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        geoms.extend(shape(f["geometry"]) for f in data["features"] if f.get("geometry"))
    return geoms


def rasterize(geoms: list) -> np.ndarray:
    land = np.zeros((ROWS, COLS), dtype=bool)
    lats = -90 + (np.arange(ROWS) + 0.5) * RES
    lons = -180 + (np.arange(COLS) + 0.5) * RES
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    for g in geoms:
        minx, miny, maxx, maxy = g.bounds
        r0, r1 = max(int((miny + 90) / RES), 0), min(int((maxy + 90) / RES) + 1, ROWS)
        c0, c1 = max(int((minx + 180) / RES), 0), min(int((maxx + 180) / RES) + 1, COLS)
        shapely.prepare(g)
        land[r0:r1, c0:c1] |= shapely.contains_xy(g, lon_grid[r0:r1, c0:c1], lat_grid[r0:r1, c0:c1])
        # Islands smaller than a cell contain no cell centre; mark the cells holding their vertices.
        coords = shapely.get_coordinates(g)
        rows = np.clip(((coords[:, 1] + 90) / RES).astype(int), 0, ROWS - 1)
        cols = np.clip(((coords[:, 0] + 180) / RES).astype(int), 0, COLS - 1)
        land[rows, cols] = True
    return land


def dilate(land: np.ndarray, km: float) -> np.ndarray:
    out = land.copy()
    dy_max = math.ceil(km / (KM_PER_DEG * RES))
    lats = -90 + (np.arange(ROWS) + 0.5) * RES
    for dy in range(-dy_max, dy_max + 1):
        rem_km = math.sqrt(max(km**2 - (abs(dy) * RES * KM_PER_DEG) ** 2, 0.0))
        shifted = np.zeros_like(land)
        if dy >= 0:
            shifted[dy:] = land[: ROWS - dy]
        else:
            shifted[:dy] = land[-dy:]
        padded = np.concatenate([shifted, shifted, shifted], axis=1).astype(np.int32)
        csum = np.concatenate([np.zeros((ROWS, 1), np.int32), np.cumsum(padded, axis=1)], axis=1)
        for r in range(ROWS):
            if not shifted[r].any():
                continue
            cos_lat = max(math.cos(math.radians(lats[r])), 1e-6)
            k = min(int(rem_km / (KM_PER_DEG * RES * cos_lat)), COLS // 2)
            idx = np.arange(COLS) + COLS
            out[r] |= (csum[r, idx + k + 1] - csum[r, idx - k]) > 0
    return out


def main(paths: list[str]) -> None:
    if not paths:
        sys.exit(__doc__)
    land = rasterize(load_geoms(paths))
    mask = dilate(land, DILATE_KM)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT, bits=np.packbits(mask, axis=1), rows=ROWS, cols=COLS, res=RES, dilate_km=DILATE_KM)
    print(f"land cells {land.mean():.3f}, near-land cells {mask.mean():.3f}, written {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1:])
