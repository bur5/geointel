"""Population by admin-1 region and by 0.25° cell (built by ``popgrid_build`` from GHSL).

The daily pipeline reads the cached JSON (``cache/popgrid.json`` on the risk-data branch).
Without it, the regional layer falls back to the city-based proxy and absolute thresholds.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

VERSION = 1
CELL_DEG = 0.25
FILE = "popgrid.json"
SOURCE = "GHSL GHS-POP R2023A (European Commission, JRC; CC BY 4.0)"


def cell_of(lat: float, lon: float) -> tuple[int, int]:
    """Row from the north pole and column from 180° west of the 0.25° cell."""
    row = min(max(int((90.0 - lat) // CELL_DEG), 0), int(180 / CELL_DEG) - 1)
    col = min(max(int((lon + 180.0) // CELL_DEG), 0), int(360 / CELL_DEG) - 1)
    return row, col


class PopGrid:
    def __init__(self, payload: Mapping):
        self.source = str(payload.get("source") or SOURCE)
        self.regions: dict[str, dict[str, int]] = {
            iso3: {code: int(n) for code, n in codes.items()}
            for iso3, codes in (payload.get("regions") or {}).items()
        }
        self.cells: dict[str, dict[str, list[tuple[int, int, int]]]] = {
            iso3: {
                code: [(int(r), int(c), int(n)) for r, c, n in items]
                for code, items in codes.items()
            }
            for iso3, codes in (payload.get("cells") or {}).items()
        }

    def region_population(self, iso3: str) -> dict[str, int]:
        return dict(self.regions.get(iso3) or {})

    def zone_population(
        self, iso3: str, code: str, hot_cells: Iterable[tuple[int, int]], radius: int = 1
    ) -> int:
        """People in the region's cells within ``radius`` cells of a cell with deaths."""
        hot = set(hot_cells)
        if not hot:
            return 0
        near = {
            (r + dr, c + dc)
            for r, c in hot
            for dr in range(-radius, radius + 1)
            for dc in range(-radius, radius + 1)
        }
        return sum(n for r, c, n in (self.cells.get(iso3) or {}).get(code, []) if (r, c) in near)


def load(path: Path) -> PopGrid | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if payload.get("version") != VERSION or not payload.get("regions"):
        return None
    return PopGrid(payload)
