"""Preset regions. City presets are single points; state presets are approximate bounding boxes."""

from __future__ import annotations

from ..models.schemas import BBox, PresetRegion

_CITIES = [
    ("hyderabad", "Hyderabad", 17.385, 78.4867),
    ("mumbai", "Mumbai", 19.076, 72.8777),
    ("delhi", "Delhi", 28.6139, 77.209),
    ("bengaluru", "Bengaluru", 12.9716, 77.5946),
    ("chennai", "Chennai", 13.0827, 80.2707),
    ("visakhapatnam", "Visakhapatnam", 17.6868, 83.2185),
    ("kolkata", "Kolkata", 22.5726, 88.3639),
    ("pune", "Pune", 18.5204, 73.8567),
    ("ahmedabad", "Ahmedabad", 23.0225, 72.5714),
    ("jaipur", "Jaipur", 26.9124, 75.7873),
    ("nagpur", "Nagpur", 21.1458, 79.0882),
    ("lucknow", "Lucknow", 26.8467, 80.9462),
]

# (id, name, south, west, north, east) - coarse rectangles, not administrative boundaries.
_STATES = [
    ("telangana", "Telangana (approx. box)", 15.8, 77.2, 19.9, 81.8),
    ("andhra_pradesh", "Andhra Pradesh (approx. box)", 12.6, 76.8, 19.2, 84.8),
    ("tamil_nadu", "Tamil Nadu (approx. box)", 8.1, 76.2, 13.6, 80.3),
    ("rajasthan", "Rajasthan (approx. box)", 23.1, 69.5, 30.2, 78.3),
    ("maharashtra", "Maharashtra (approx. box)", 15.6, 72.6, 22.0, 80.9),
    ("odisha", "Odisha (approx. box)", 17.8, 81.4, 22.6, 87.5),
]


def preset_regions() -> list[PresetRegion]:
    regions = [PresetRegion(id=i, name=n, kind="city", latitude=lat, longitude=lon) for i, n, lat, lon in _CITIES]
    for i, n, s, w, no, e in _STATES:
        regions.append(
            PresetRegion(
                id=i,
                name=n,
                kind="state",
                latitude=round((s + no) / 2, 4),
                longitude=round((w + e) / 2, 4),
                bbox=BBox(south=s, west=w, north=no, east=e),
            )
        )
    return regions
