"""Piirkondade üüritootluse arvutus."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from statistics import median

from . import config, regions
from .regions import Location

SALE, RENT = config.DEAL_SALE, config.DEAL_RENT
LISTING_LEVELS = ("subdistrict", "district", "city", "county")

Key = tuple[str, tuple[str, ...], str]  # (tase, rada, toarühm)


def room_group(rooms: int | None) -> str | None:
    if rooms is None or rooms < 1:
        return None
    return "4+" if rooms >= 4 else str(rooms)


def _in_range(value, bounds) -> bool:
    return value is not None and bounds[0] <= value <= bounds[1]


def clean(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        bounds = config.SALE_M2_RANGE if r["deal_type"] == SALE else config.RENT_M2_RANGE
        if _in_range(r["area_m2"], config.AREA_RANGE) and _in_range(r["price_per_m2"], bounds):
            out.append(r)
    return out


def _paths(county: str, loc: Location) -> list[tuple[str, tuple[str, ...]]]:
    paths = [("county", (county,))]
    if not regions.is_center(county, loc):
        paths.append(("county_ex_center", (county,)))
    if loc.city:
        paths.append(("city", (county, loc.city)))
        if loc.district:
            paths.append(("district", (county, loc.city, loc.district)))
            if loc.subdistrict:
                paths.append(("subdistrict", (county, loc.city, loc.district, loc.subdistrict)))
    return paths


def _summarize(sale: list[float], rent: list[float]) -> dict:
    sale_m2 = median(sale) if sale else None
    rent_m2 = median(rent) if rent else None
    enough = len(sale) >= config.MIN_SAMPLES and len(rent) >= config.MIN_SAMPLES
    return {
        "sale_m2": sale_m2, "rent_m2": rent_m2, "n_sale": len(sale), "n_rent": len(rent),
        "yield": rent_m2 * 12 / sale_m2 if enough else None,
    }


def _run_stats(rows: list[dict]) -> dict[Key, dict]:
    buckets: dict[Key, tuple[list, list]] = {}
    for r in rows:
        groups = ["all"] + ([g] if (g := room_group(r["rooms"])) else [])
        for level, path in _paths(r["county"], r["loc"]):
            for g in groups:
                sale, rent = buckets.setdefault((level, path, g), ([], []))
                (sale if r["deal_type"] == SALE else rent).append(r["price_per_m2"])
    return {key: _summarize(sale, rent) for key, (sale, rent) in buckets.items()}


def _region_name(level: str, path: tuple[str, ...]) -> str:
    if level == "county_ex_center":
        return f"{path[0]} (v.a {config.COUNTY_CENTERS[path[0]]})"
    return path[-1]


def _round(value, digits):
    return round(value, digits) if value is not None else None


def _best_listings(rows: list[dict], stats: dict[Key, dict]) -> list[dict]:
    out = []
    for r in rows:
        group = room_group(r["rooms"])
        if r["deal_type"] != SALE or group is None:
            continue
        paths = dict(_paths(r["county"], r["loc"]))
        for level in LISTING_LEVELS:
            s = stats.get((level, paths.get(level), group)) if level in paths else None
            if s and s["n_rent"] >= config.MIN_SAMPLES:
                rent = r["area_m2"] * s["rent_m2"]
                out.append({
                    "id": r["id"], "url": r["url"], "address": r["address"],
                    "path": list(max(paths.values(), key=len)), "rooms": r["rooms"],
                    "area_m2": r["area_m2"], "price": r["price"],
                    "rent_estimate": round(rent, 2), "yield": round(rent * 12 / r["price"], 4),
                    "rent_level": level,
                })
                break
    out.sort(key=lambda x: x["yield"], reverse=True)
    return out[: config.TOP_LISTINGS]


def compute(store, generated_at: str | None = None) -> dict:
    runs = store.runs()
    rows_by_run = {run["id"]: clean(store.observations(run["id"])) for run in runs}

    all_rows = [r for rows in rows_by_run.values() for r in rows]
    for r in all_rows:
        r["loc"] = regions.parse(r["location"] or "")
    district_map = regions.build_district_map(r["loc"] for r in all_rows)
    for r in all_rows:
        r["loc"] = regions.fill_district(r["loc"], district_map)

    stats_by_run = {run_id: _run_stats(rows) for run_id, rows in rows_by_run.items()}
    run_ids = [run["id"] for run in runs]

    keys = {key for stats in stats_by_run.values() for key in stats}
    region_rows = []
    for key in keys:
        level, path, group = key
        per_run = [stats_by_run[rid][key] for rid in run_ids if key in stats_by_run[rid]]
        valid = [s["yield"] for s in per_run if s["yield"] is not None]
        latest = per_run[-1]
        region_rows.append({
            "level": level, "name": _region_name(level, path), "path": list(path), "rooms": group,
            "yield_median": _round(median(valid), 4) if valid else None,
            "yield_latest": _round(latest["yield"], 4),
            "valid_runs": len(valid),
            "sale_m2": _round(latest["sale_m2"], 1), "rent_m2": _round(latest["rent_m2"], 2),
            "n_sale": latest["n_sale"], "n_rent": latest["n_rent"],
            "enough": bool(valid),
        })
    region_rows.sort(key=lambda x: (x["level"], x["path"], x["rooms"]))

    listings = []
    if run_ids:
        last = run_ids[-1]
        listings = _best_listings(rows_by_run[last], stats_by_run[last])

    return {
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "runs": [{k: run[k] for k in ("id", "started_at", "complete", "counties_ok")} for run in runs],
        "regions": region_rows,
        "listings": listings,
    }


def write_results(results: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
