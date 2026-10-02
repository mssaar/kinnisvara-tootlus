"""Tallinna hinna-kauguse mudel: keskpunkt, kauguse mõju ja alahinnatud objektid."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from statistics import median

import numpy as np

from . import analyze, regions
from .geocode import street_query

VABADUSE = (59.4339, 24.7445)
KNOTS = (2.0, 5.0, 8.0)
EFFECT_DISTANCES = (1, 3, 6)
UNDERVALUED = -0.15
MIN_SALE = 50
MIN_RENT = 30
MIN_SUBDISTRICT = 5
LAT_RANGE = (59.35, 59.50)
LON_RANGE = (24.55, 24.95)
TYPICAL = {"rooms": 2, "area_m2": 50.0, "build_year": 2000, "condition": "heas korras", "floor": 3}

ROOM_LEVELS = ("2", "3", "4+")                       # baas "1"
YEAR_LEVELS = ("<1940", "1940-1990", ">2010", "?")   # baas "1991-2010"
CONDITION_GROUPS = {
    "uus": "new", "valmis": "new",
    "renoveeritud": "renovated", "san. remont tehtud": "renovated",
    "heas korras": "good",
    "keskmises seisukorras": "average",
    "vajab san. remonti": "needs_work", "vajab renoveerimist": "needs_work", "alustamata ehitus": "needs_work",
}
CONDITION_LEVELS = ("new", "renovated", "average", "needs_work", "?")  # baas "good"


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def _year_group(year) -> str:
    if year is None:
        return "?"
    if year < 1940:
        return "<1940"
    if year <= 1990:
        return "1940-1990"
    if year <= 2010:
        return "1991-2010"
    return ">2010"


def _distance_columns(d: np.ndarray) -> list[np.ndarray]:
    return [d] + [np.maximum(d - k, 0.0) for k in KNOTS]


def features(rows: list[dict], dist: np.ndarray) -> np.ndarray:
    return _with_distance(_static_columns(rows), dist)


def _with_distance(static: np.ndarray, dist) -> np.ndarray:
    d = np.asarray(dist, dtype=float)
    return np.column_stack([np.ones(len(d))] + _distance_columns(d) + [static])


def _static_columns(rows: list[dict]) -> np.ndarray:
    """Kaugusest sõltumatud veerud — arvutatakse üks kord, keskpunkti otsingus taaskasutatakse."""
    cols = []
    rooms = [analyze.room_group(r["rooms"]) for r in rows]
    cols += [np.array([g == level for g in rooms], dtype=float) for level in ROOM_LEVELS]
    cols.append(np.log(np.array([r["area_m2"] for r in rows], dtype=float)))
    years = [_year_group(r.get("build_year")) for r in rows]
    cols += [np.array([y == level for y in years], dtype=float) for level in YEAR_LEVELS]
    conds = [CONDITION_GROUPS.get(r.get("condition"), "?") for r in rows]
    cols += [np.array([c == level for c in conds], dtype=float) for level in CONDITION_LEVELS]
    floors = [r.get("floor") for r in rows]
    cols.append(np.array([f == 1 for f in floors], dtype=float))
    cols.append(np.array([f is None for f in floors], dtype=float))
    return np.column_stack(cols)


def _fit(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float, float]:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    sse = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    return beta, sse, (1 - sse / sst) if sst > 0 else 0.0


def _coords(rows):
    return np.array([r["lat"] for r in rows]), np.array([r["lon"] for r in rows])


def _grid(lo, hi, step):
    return np.arange(lo, hi + step / 2, step)


def find_center(rows: list[dict]) -> tuple[float, float]:
    y = np.log(np.array([r["price_per_m2"] for r in rows], dtype=float))
    lats, lons = _coords(rows)
    static = _static_columns(rows)

    def _sse_at(lat, lon) -> float:
        return _fit(_with_distance(static, haversine_km(lats, lons, lat, lon)), y)[1]

    km_lat = 1 / 111.32
    km_lon = 1 / (111.32 * math.cos(math.radians(sum(LAT_RANGE) / 2)))

    def search(lat_values, lon_values):
        best = (math.inf, None, None)
        for lat in lat_values:
            for lon in lon_values:
                sse = _sse_at(lat, lon)
                if sse < best[0]:
                    best = (sse, float(lat), float(lon))
        return best[1], best[2]

    lat, lon = search(_grid(*LAT_RANGE, 0.25 * km_lat), _grid(*LON_RANGE, 0.25 * km_lon))
    return search(_grid(lat - 0.3 * km_lat, lat + 0.3 * km_lat, 0.05 * km_lat),
                  _grid(lon - 0.3 * km_lon, lon + 0.3 * km_lon, 0.05 * km_lon))


def _slope(beta: np.ndarray, d: float) -> float:
    # beta[1] = kalle 0 km-st; beta[2..4] lisanduvad pärast murdepunkte
    return float(beta[1] + sum(beta[2 + i] for i, k in enumerate(KNOTS) if d > k))


def _effects(beta: np.ndarray) -> dict[str, float]:
    return {str(d): round(math.exp(_slope(beta, d) * 0.1) - 1, 5) for d in EFFECT_DISTANCES}


def _predict_m2(rows, beta, lat, lon) -> np.ndarray:
    lats, lons = _coords(rows)
    return np.exp(features(rows, haversine_km(lats, lons, lat, lon)) @ beta)


def fit_run(sale: list[dict], rent: list[dict]) -> dict | None:
    if len(sale) < MIN_SALE or len(rent) < MIN_RENT:
        return None
    lat, lon = find_center(sale)

    def fit_for(rows):
        lats, lons = _coords(rows)
        X = features(rows, haversine_km(lats, lons, lat, lon))
        y = np.log(np.array([r["price_per_m2"] for r in rows], dtype=float))
        return _fit(X, y)

    beta_s, _, r2_s = fit_for(sale)
    beta_r, _, r2_r = fit_for(rent)

    typical = [dict(TYPICAL) for _ in range(61)]
    dists = np.arange(61) * 0.25
    tx = features(typical, dists)
    curve = [{"d": round(float(d), 2), "sale_m2": round(float(s), 1), "rent_m2": round(float(r), 2)}
             for d, s, r in zip(dists, np.exp(tx @ beta_s), np.exp(tx @ beta_r))]

    pred_sale_m2 = _predict_m2(sale, beta_s, lat, lon)
    pred_rent_m2 = _predict_m2(sale, beta_r, lat, lon)
    scored = []
    for row, ps, pr in zip(sale, pred_sale_m2, pred_rent_m2):
        predicted_price = float(ps) * row["area_m2"]
        rent_est = float(pr) * row["area_m2"]
        scored.append({
            "id": row["id"], "url": row["url"], "address": row["address"],
            "lat": round(row["lat"], 6), "lon": round(row["lon"], 6),
            "rooms": row["rooms"], "area_m2": row["area_m2"], "price": row["price"],
            "predicted_price": round(predicted_price), "residual": round(row["price"] / predicted_price - 1, 4),
            "rent_estimate": round(rent_est, 2), "yield": round(rent_est * 12 / row["price"], 4),
            "subdistrict": row.get("asum"),
            "floor": row.get("floor"), "floors_total": row.get("floors_total"),
        })

    by_asum: dict[str, list[dict]] = {}
    for s in scored:
        if s["subdistrict"]:
            by_asum.setdefault(s["subdistrict"], []).append(s)
    subdistricts = sorted(
        ({"name": name, "lat": round(float(np.mean([x["lat"] for x in xs])), 6),
          "lon": round(float(np.mean([x["lon"] for x in xs])), 6), "n": len(xs),
          "residual_median": round(median(x["residual"] for x in xs), 4)}
         for name, xs in by_asum.items() if len(xs) >= MIN_SUBDISTRICT),
        key=lambda x: x["residual_median"],
    )

    listings = sorted((s for s in scored if s["residual"] <= UNDERVALUED), key=lambda s: s["residual"])
    return {
        "center": {"lat": round(lat, 6), "lon": round(lon, 6)},
        "center_offset_m": round(float(haversine_km(lat, lon, *VABADUSE)) * 1000),
        "effects": {"sale": _effects(beta_s), "rent": _effects(beta_r)},
        "r2": {"sale": round(r2_s, 3), "rent": round(r2_r, 3)},
        "n": {"sale": len(sale), "rent": len(rent)},
        "curve": curve, "subdistricts": subdistricts, "listings": listings,
    }


def _tallinn_rows(store, run_id: int) -> list[dict]:
    rows = analyze.clean(store.observations(run_id))
    return [r for r in rows if regions.parse(r["location"] or "").city == "Tallinn"]


def queries(store) -> set[str]:
    out = set()
    for run in store.runs():
        for r in _tallinn_rows(store, run["id"]):
            q = street_query(r["address"] or "", r["location"] or "")
            if q:
                out.add(q)
    return out


def _in_range(geo) -> bool:
    return LAT_RANGE[0] <= geo.lat <= LAT_RANGE[1] and LON_RANGE[0] <= geo.lon <= LON_RANGE[1]


def compute(store, geocoder, generated_at: str | None = None) -> dict:
    attrs = store.listing_attrs()
    run_results = []
    for run in store.runs():
        sale, rent, missing = [], [], 0
        for r in _tallinn_rows(store, run["id"]):
            q = street_query(r["address"] or "", r["location"] or "")
            geo = geocoder.lookup(q) if q else None
            if geo is None or not _in_range(geo):
                missing += 1
                continue
            row = dict(r, lat=geo.lat, lon=geo.lon,
                       asum=geo.asum or regions.parse(r["location"] or "").subdistrict,
                       **attrs.get((r["id"], r["deal_type"]), {}))
            (sale if r["deal_type"] == 1 else rent).append(row)
        fitted = fit_run(sale, rent)
        if fitted is not None:
            fitted["n"]["not_geocoded"] = missing
            run_results.append((run, fitted))

    summaries = [{"run_id": run["id"], "started_at": run["started_at"],
                  **{k: f[k] for k in ("center", "center_offset_m", "effects", "r2", "n")}}
                 for run, f in run_results]
    med = None
    if summaries:
        med = {
            "center": {k: round(median(s["center"][k] for s in summaries), 6) for k in ("lat", "lon")},
            "effects": {deal: {d: round(median(s["effects"][deal][d] for s in summaries), 5)
                               for d in summaries[0]["effects"][deal]} for deal in ("sale", "rent")},
        }
    latest = run_results[-1][1] if run_results else {"curve": [], "subdistricts": [], "listings": []}
    return {
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "runs": summaries, "median": med,
        "curve": latest["curve"], "subdistricts": latest["subdistricts"], "listings": latest["listings"],
    }


def write(result: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
