"""Build the population grid used by the regional layer (run rarely, in its own workflow).

Source: GHSL GHS-POP R2023A, epoch 2025, 30 arc-seconds (about 1 km), WGS84. European
Commission, Joint Research Centre; licence CC BY 4.0 (Schiavina et al., 2023).

Every 1-km pixel is assigned to a Natural Earth admin-1 region by rasterising the same
polygons that ``RegionIndex`` uses, so region totals count rural people too (the earlier
proxy summed cities of 15,000+). The output also keeps population per 0.25° cell and region,
so that a conflict can be measured against the people who live near it, not the whole
region (Fable round 4, 3.3).

Needs ``numpy`` and ``rasterio``, which the daily pipeline does not install; the pipeline
only reads the JSON this module writes (``popgrid.load``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from geointel.risk.popgrid import CELL_DEG, VERSION
from geointel.risk.regions import RegionIndex

STRIP_ROWS = 120  # one degree of 30-arc-second rows


def build(tif: str, regions_geojson: bytes) -> dict:
    import numpy as np
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    from rasterio.windows import Window

    index = RegionIndex.from_bytes(regions_geojson)
    keys: list[tuple[str, str]] = [("", "")]  # id 0 = no region
    shapes = []  # (bbox, geometry, id)
    for iso3, feats in index.by_country.items():
        for bbox, rings, names in feats:
            keys.append((iso3, names[2]))
            geometry = {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}
            shapes.append((bbox, geometry, len(keys) - 1))

    region_pop = np.zeros(len(keys), dtype=np.float64)
    cells: dict[int, float] = {}
    unassigned = 0.0
    total = 0.0
    with rasterio.open(tif) as src:
        step = src.transform.a  # pixel width in degrees
        per_cell = round(CELL_DEG / step)  # pixels per 0.25° cell (30)
        row_offset = round((90 - src.transform.f) / step)  # pixel rows above the raster
        col_offset = round((src.transform.c + 180) / step)
        nodata = src.nodata
        for row0 in range(0, src.height, STRIP_ROWS):
            rows = min(STRIP_ROWS, src.height - row0)
            data = src.read(1, window=Window(0, row0, src.width, rows)).astype(np.float64)
            if nodata is not None:
                data[data == nodata] = 0.0
            data[data < 0] = 0.0
            if not data.any():
                continue
            top = src.transform.f + row0 * src.transform.e
            bottom = top + rows * src.transform.e
            left = src.transform.c
            strip = [
                (geom, ident)
                for (x0, y0, x1, y1), geom, ident in shapes
                if y1 >= bottom and y0 <= top
            ]
            ids = (
                rasterize(
                    strip,
                    out_shape=(rows, src.width),
                    transform=Affine(step, 0, left, 0, src.transform.e, top),
                    fill=0,
                    dtype="int32",
                )
                if strip
                else np.zeros((rows, src.width), dtype=np.int32)
            )
            total += float(data.sum())
            unassigned += float(data[ids == 0].sum())
            region_pop += np.bincount(ids.ravel(), weights=data.ravel(), minlength=len(keys))
            # 0.25° cell index: row from the north pole, column from 180° west.
            r_idx = (np.arange(rows) + row0 + row_offset) // per_cell
            c_idx = (np.arange(src.width) + col_offset) // per_cell
            mask = (data > 0) & (ids > 0)
            rr, cc = np.nonzero(mask)
            if rr.size == 0:
                continue
            key = (r_idx[rr].astype(np.int64) * 1440 + c_idx[cc]) * len(keys) + ids[rr, cc]
            uniq, inverse = np.unique(key, return_inverse=True)
            sums = np.bincount(inverse, weights=data[rr, cc])
            for k, v in zip(uniq.tolist(), sums.tolist(), strict=True):
                cells[k] = cells.get(k, 0.0) + v
    regions: dict[str, dict[str, int]] = {}
    for ident, (iso3, code) in enumerate(keys):
        if ident and region_pop[ident] >= 1:
            regions.setdefault(iso3, {})[code] = int(round(region_pop[ident]))
    by_region: dict[str, dict[str, list[list[int]]]] = {}
    for k, v in cells.items():
        if v < 1:
            continue
        cell, ident = divmod(k, len(keys))
        row, col = divmod(cell, 1440)
        iso3, code = keys[ident]
        by_region.setdefault(iso3, {}).setdefault(code, []).append([row, col, int(round(v))])
    return {
        "version": VERSION,
        "source": "GHSL GHS-POP R2023A, epoch 2025, 30 arc-seconds (JRC, CC BY 4.0)",
        "cell_deg": CELL_DEG,
        "total": int(round(total)),
        "unassigned": int(round(unassigned)),
        "regions": regions,
        "cells": by_region,
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    tif, regions_path, out = args
    result = build(tif, Path(regions_path).read_bytes())
    Path(out).write_text(json.dumps(result, separators=(",", ":")))
    share = result["unassigned"] / max(result["total"], 1)
    print(
        f"[popgrid] total {result['total']:,}, outside admin-1 polygons {share:.2%}, "
        f"countries {len(result['regions'])}, file {Path(out).stat().st_size:,} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
