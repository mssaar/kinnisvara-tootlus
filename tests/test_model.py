import math

import numpy as np
import pytest

from tootlus import model

CENTER = (59.4370, 24.7450)
KM_LAT = 1 / 111.32
KM_LON = 1 / (111.32 * math.cos(math.radians(59.43)))


def synth(n, base, slope, seed, kind, undervalued_id=None, distance_effect=None):
    if distance_effect is None:
        distance_effect = lambda d: slope * d
    rng = np.random.default_rng(seed)
    rows = []
    conditions = ["heas korras", "uus", "renoveeritud", "keskmises seisukorras", None]
    for i in range(n):
        r_km = rng.uniform(0.2, 9.0)
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
