import json
import math
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest

from tootlus import model
from tootlus.geocode import Geocoder
from tootlus.parser import Listing
from tootlus.store import Store

CENTER = (59.4370, 24.7450)
KM_LAT = 1 / 111.32
KM_LON = 1 / (111.32 * math.cos(math.radians(59.43)))


def synth(n, base, slope, seed, kind, undervalued_id=None, distance_effect=None, r_max=9.0):
    if distance_effect is None:
        distance_effect = lambda d: slope * d
    rng = np.random.default_rng(seed)
    rows = []
    conditions = ["heas korras", "uus", "renoveeritud", "keskmises seisukorras", None]
    for i in range(n):
        r_km = rng.uniform(0.2, r_max)
        ang = rng.uniform(0, 2 * math.pi)
        lat = CENTER[0] + r_km * math.sin(ang) * KM_LAT
        lon = CENTER[1] + r_km * math.cos(ang) * KM_LON
        rooms = int(rng.integers(1, 5))
        area = float(rng.uniform(25, 110))
        d = float(model.haversine_km(lat, lon, *CENTER))
        log_m2 = math.log(base) + distance_effect(d) + 0.08 * (rooms == 3) + rng.normal(0, 0.05)
        if undervalued_id is not None and i == 0:
            log_m2 += math.log(0.7)
        m2 = math.exp(log_m2)
        rows.append({
            "id": (undervalued_id if (undervalued_id is not None and i == 0) else seed * 100000 + i),
            "url": f"https://www.kv.ee/x-{i}", "address": f"Tn {i}, Tallinn",
            "lat": lat, "lon": lon, "rooms": rooms, "area_m2": area,
            "price": m2 * area, "price_per_m2": m2,
            "build_year": int(rng.choice([1930, 1970, 2000, 2020])), "condition": conditions[i % 5],
            "floor": int(rng.integers(1, 9)), "asum": f"Asum{int(r_km)}",
        })
    return rows


def test_haversine():
    assert model.haversine_km(59.4339, 24.7445, 59.4339, 24.7445) == pytest.approx(0)
    assert model.haversine_km(59.0, 24.0, 59.1, 24.0) == pytest.approx(11.12, abs=0.02)


def test_finds_center_and_effects():
    sale = synth(1500, 3500, -0.08, seed=1, kind="sale", undervalued_id=777)
    rent = synth(600, 16, -0.05, seed=2, kind="rent")
    res = model.fit_run(sale, rent)
    c = res["center"]
    assert model.haversine_km(c["lat"], c["lon"], *CENTER) * 1000 < 100
    expected_sale = math.exp(-0.08 * 0.1) - 1
    expected_rent = math.exp(-0.05 * 0.1) - 1
    for d in ("1", "3", "6"):
        assert res["effects"]["sale"][d] == pytest.approx(expected_sale, rel=0.10)
        assert res["effects"]["rent"][d] == pytest.approx(expected_rent, rel=0.10)
    assert res["r2"]["sale"] > 0.8
    assert res["n"] == {"sale": 1500, "rent": 600}
    ids = [l["id"] for l in res["listings"]]
    assert ids[0] == 777
    assert all(l["residual"] <= -0.15 for l in res["listings"])
    first = res["listings"][0]
    assert first["residual"] == pytest.approx(-0.3, abs=0.06)
    assert first["yield"] == pytest.approx(first["rent_estimate"] * 12 / first["price"], abs=1e-4)
    expected_offset = model.haversine_km(c["lat"], c["lon"], *model.VABADUSE) * 1000
    assert res["center_offset_m"] == round(expected_offset)


def test_curve_and_subdistricts():
    res = model.fit_run(synth(800, 3500, -0.08, seed=3, kind="sale"), synth(300, 16, -0.05, seed=4, kind="rent"))
    curve = res["curve"]
    assert curve[0]["d"] == 0 and curve[-1]["d"] == 15
    assert len(curve) == 61
    assert curve[0]["sale_m2"] > curve[20]["sale_m2"] > curve[40]["sale_m2"]
    assert curve[0]["rent_m2"] > curve[40]["rent_m2"]
    subs = res["subdistricts"]
    assert subs and all(s["n"] >= 5 for s in subs)
    assert {"name", "lat", "lon", "n", "residual_median"} <= set(subs[0])


def test_piecewise_slope_change():
    def piecewise_distance_effect(d):
        # Slope is -0.12/km for d <= 5 km, -0.03/km for d > 5 km, continuous at 5 km
        if d <= 5:
            return -0.12 * d
        else:
            return -0.45 - 0.03 * d

    sale = synth(1500, 3500, -0.08, seed=11, kind="sale", distance_effect=piecewise_distance_effect)
    rent = synth(600, 16, -0.05, seed=12, kind="rent")
    res = model.fit_run(sale, rent)

    # At 3 km, the true slope is -0.12
    expected_sale_3 = math.exp(-0.12 * 0.1) - 1
    # At 6 km, the true slope is -0.03
    expected_sale_6 = math.exp(-0.03 * 0.1) - 1

    assert res["effects"]["sale"]["3"] == pytest.approx(expected_sale_3, rel=0.2)
    assert res["effects"]["sale"]["6"] == pytest.approx(expected_sale_6, rel=0.2)

    # The two effects should differ clearly
    assert abs(res["effects"]["sale"]["3"] - res["effects"]["sale"]["6"]) > 0.005


def test_rare_categories_do_not_break_fit():
    sale = synth(200, 3500, -0.08, seed=5, kind="sale")
    rent = synth(100, 16, -0.05, seed=6, kind="rent")
    for r in sale + rent:
        r["condition"] = "heas korras"
        r["build_year"] = None
        r["floor"] = None
    res = model.fit_run(sale, rent)
    assert res is not None
    assert all(math.isfinite(v) for v in res["effects"]["sale"].values())

    # Assert sale effects match expected constant slope
    expected_sale = math.exp(-0.08 * 0.1) - 1
    for d in ("1", "3", "6"):
        assert res["effects"]["sale"][d] == pytest.approx(expected_sale, rel=0.15)

    # Assert both r2 values are finite
    assert math.isfinite(res["r2"]["sale"])
    assert math.isfinite(res["r2"]["rent"])


def test_too_few_rows():
    assert model.fit_run(synth(49, 3500, -0.08, seed=7, kind="sale"), synth(100, 16, -0.05, seed=8, kind="rent")) is None
    assert model.fit_run(synth(100, 3500, -0.08, seed=9, kind="sale"), synth(29, 16, -0.05, seed=10, kind="rent")) is None


def _store_with(sale_rows, rent_rows, other_city=0):
    s = Store(":memory:")
    r = s.start_run("2026-10-01T00:00:00")
    def to_listing(row, i):
        q = f"Tn {i}"
        return Listing(row["id"], row["url"], f"{q}, Kesklinn, Tallinn", "Kesklinn, Tallinn", row["rooms"],
                       round(row["area_m2"], 1), round(row["price"]), row["floor"], row["build_year"], row["condition"])
    sale = [to_listing(row, i) for i, row in enumerate(sale_rows)]
    rent = [to_listing(row, 10000 + i) for i, row in enumerate(rent_rows)]
    extra = [Listing(900000 + i, "u", f"Tn {i}, Narva", "Narva", 2, 50.0, 30000, 1, 1970, None) for i in range(other_city)]
    s.save_listings(r, 1, "Harjumaa", sale + extra)
    s.save_listings(r, 2, "Harjumaa", rent)
    s.finish_run(r, ["Harjumaa"], True)
    coords = {f"Tn {i}, Tallinn": row for i, row in enumerate(sale_rows)}
    coords.update({f"Tn {10000 + i}, Tallinn": row for i, row in enumerate(rent_rows)})
    def fetch(url):
        q = parse_qs(urlparse(url).query)["address"][0]
        row = coords.get(q)
        if row is None:
            return {"addresses": []}
        return {"addresses": [{"viitepunkt_b": str(row["lat"]), "viitepunkt_l": str(row["lon"]), "asum": row["asum"] + " asum"}]}
    g = Geocoder(s.conn, fetch=fetch, sleep=lambda x: None)
    return s, g


def test_compute_from_store(tmp_path):
    s, g = _store_with(synth(300, 3500, -0.08, seed=11, kind="sale", r_max=6.5), synth(120, 16, -0.05, seed=12, kind="rent", r_max=6.5), other_city=3)
    qs = model.queries(s)
    assert "Tn 0, Tallinn" in qs and not any("Narva" in q for q in qs)
    g.geocode_missing(qs, progress=lambda m: None)
    res = model.compute(s, g, generated_at="t")
    assert res["generated_at"] == "t"
    assert len(res["runs"]) == 1
    run = res["runs"][0]
    assert run["n"] == {"sale": 300, "rent": 120, "not_geocoded": 0}
    assert set(run) >= {"run_id", "started_at", "center", "center_offset_m", "effects", "r2", "n"}
    assert res["median"]["effects"]["sale"]["3"] == run["effects"]["sale"]["3"]
    assert res["curve"] and res["subdistricts"]
    out = tmp_path / "data" / "model.json"
    model.write(res, out)
    assert json.loads(out.read_text(encoding="utf-8"))["generated_at"] == "t"


def test_compute_too_little_data():
    s, g = _store_with(synth(10, 3500, -0.08, seed=13, kind="sale", r_max=6.5), synth(10, 16, -0.05, seed=14, kind="rent", r_max=6.5))
    g.geocode_missing(model.queries(s), progress=lambda m: None)
    res = model.compute(s, g)
    assert res["runs"] == [] and res["median"] is None
    assert res["curve"] == [] and res["subdistricts"] == [] and res["listings"] == []


def test_compute_counts_not_geocoded():
    sale = synth(300, 3500, -0.08, seed=15, kind="sale", r_max=6.5)
    s, g = _store_with(sale, synth(120, 16, -0.05, seed=16, kind="rent", r_max=6.5))
    g.geocode_missing([q for q in model.queries(s) if q != "Tn 0, Tallinn"], progress=lambda m: None)
    res = model.compute(s, g)
    assert res["runs"][0]["n"]["not_geocoded"] == 1
    assert res["runs"][0]["n"]["sale"] == 299


def test_compute_treats_out_of_range_geocode_as_missing():
    sale = synth(300, 3500, -0.08, seed=17, kind="sale", r_max=6.5)
    sale[0] = dict(sale[0], lat=58.38, lon=26.72)  # Tartu
    s, g = _store_with(sale, synth(120, 16, -0.05, seed=18, kind="rent", r_max=6.5))
    g.geocode_missing(model.queries(s), progress=lambda m: None)
    res = model.compute(s, g)
    assert res["runs"][0]["n"]["not_geocoded"] == 1
    assert res["runs"][0]["n"]["sale"] == 299


def test_compute_listings_carry_floor_and_floors_total():
    sale = synth(300, 3500, -0.08, seed=19, kind="sale", r_max=6.5, undervalued_id=777)
    s, g = _store_with(sale, synth(120, 16, -0.05, seed=20, kind="rent", r_max=6.5))
    s.backfill_attrs(1, [Listing(777, "u", "a", "l", sale[0]["rooms"], 50.0, 1, 4, sale[0]["build_year"],
                                 sale[0]["condition"], 9)])
    g.geocode_missing(model.queries(s), progress=lambda m: None)
    res = model.compute(s, g)
    assert res["listings"]
    assert all({"floor", "floors_total"} <= set(l) for l in res["listings"])
    target = next(l for l in res["listings"] if l["id"] == 777)
    assert target["floor"] == 4 and target["floors_total"] == 9
