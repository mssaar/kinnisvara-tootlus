import json

import pytest

from tootlus.analyze import compute, room_group, write_results
from tootlus.parser import Listing
from tootlus.store import Store

SALE, RENT = 1, 2
_next_id = [0]


def mk(location, price, area=50.0, rooms=2):
    _next_id[0] += 1
    i = _next_id[0]
    return Listing(i, f"https://www.kv.ee/x-{i}", f"Tn {i}, {location}", location, rooms, area, price, 1, 2000, None)


def run(store, county, sales, rents, when="2026-01-01T00:00:00"):
    r = store.start_run(when)
    store.save_listings(r, SALE, county, sales)
    store.save_listings(r, RENT, county, rents)
    store.finish_run(r, [county], True)
    return r


def region(results, level, path, rooms="all"):
    hits = [x for x in results["regions"] if x["level"] == level and x["path"] == path and x["rooms"] == rooms]
    assert len(hits) == 1, hits
    return hits[0]


KR = "Kristiine City, Kristiine, Tallinn"


def test_room_group():
    assert [room_group(r) for r in (None, 0, 1, 2, 3, 4, 7)] == [None, None, "1", "2", "3", "4+", "4+"]


def test_yield_formula_and_levels():
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000)] * 1 + [mk(KR, 100000) for _ in range(4)],
        [mk(KR, 500) for _ in range(5)])
    res = compute(s, generated_at="t")
    # 500/50 = 10 €/m² üür, 100000/50 = 2000 €/m² müük -> 10*12/2000 = 0.06
    for level, path in [("county", ["Harjumaa"]), ("city", ["Harjumaa", "Tallinn"]),
                        ("district", ["Harjumaa", "Tallinn", "Kristiine"]),
                        ("subdistrict", ["Harjumaa", "Tallinn", "Kristiine", "Kristiine City"])]:
        r = region(res, level, path)
        assert r["yield_median"] == pytest.approx(0.06)
        assert r["sale_m2"] == pytest.approx(2000)
        assert r["rent_m2"] == pytest.approx(10)
        assert (r["n_sale"], r["n_rent"], r["valid_runs"], r["enough"]) == (5, 5, 1, True)
    assert region(res, "district", ["Harjumaa", "Tallinn", "Kristiine"], "2")["yield_median"] == pytest.approx(0.06)
    assert region(res, "county", ["Harjumaa"])["name"] == "Harjumaa"


def test_below_min_samples_is_not_enough():
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)], [mk(KR, 500) for _ in range(4)])
    r = region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])
    assert r["yield_median"] is None
    assert r["enough"] is False
    assert r["n_rent"] == 4
    assert r["rent_m2"] == pytest.approx(10)


def test_median_over_runs():
    s = Store(":memory:")
    for i, rent in enumerate([500, 333.3333333, 416.6666667]):  # 0.06, 0.04, 0.05
        run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)], [mk(KR, rent) for _ in range(5)],
            when=f"202{6 + i}-01-01T00:00:00")
    r = region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])
    assert r["yield_median"] == pytest.approx(0.05)
    assert r["yield_latest"] == pytest.approx(0.05)
    assert r["valid_runs"] == 3


def test_new_rents_never_matched_with_old_prices():
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)], [mk(KR, 500) for _ in range(5)])
    run(s, "Harjumaa", [], [mk(KR, 1000) for _ in range(5)], when="2027-01-01T00:00:00")
    r = region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])
    assert r["yield_median"] == pytest.approx(0.06)
    assert r["valid_runs"] == 1
    assert r["yield_latest"] is None
    assert r["n_sale"] == 0


def test_county_without_center():
    s = Store(":memory:")
    saue = "Saue linn, Saue vald"
    run(s, "Harjumaa",
        [mk(KR, 100000) for _ in range(5)] + [mk(saue, 50000) for _ in range(5)],
        [mk(KR, 500) for _ in range(5)] + [mk(saue, 500) for _ in range(5)])
    res = compute(s)
    ex = region(res, "county_ex_center", ["Harjumaa"])
    assert ex["name"] == "Harjumaa (v.a Tallinn)"
    assert ex["yield_median"] == pytest.approx(0.12)
    assert (ex["n_sale"], ex["n_rent"]) == (5, 5)
    assert region(res, "county", ["Harjumaa"])["n_sale"] == 10


def test_outliers_removed():
    s = Store(":memory:")
    run(s, "Harjumaa",
        [mk(KR, 100000) for _ in range(5)] + [mk(KR, 1000), mk(KR, 100000, area=5), mk(KR, None)],
        [mk(KR, 500) for _ in range(5)] + [mk(KR, 100000)])
    r = region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])
    assert (r["n_sale"], r["n_rent"]) == (5, 5)


def test_missing_district_inferred_from_subdistrict():
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)] + [mk("Kristiine City, Tallinn", 100000)],
        [mk(KR, 500) for _ in range(5)])
    assert region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])["n_sale"] == 6


def test_best_listings_use_most_precise_level_with_enough_rents():
    s = Store(":memory:")
    other = "Tondi, Kristiine, Tallinn"
    run(s, "Harjumaa",
        [mk(KR, 100000) for _ in range(5)] + [mk(other, 60000)],
        [mk(KR, 500) for _ in range(5)] + [mk(other, 1000)])
    listings = {tuple(l["path"]): l for l in compute(s)["listings"]}
    tondi = listings[("Harjumaa", "Tallinn", "Kristiine", "Tondi")]
    # Tondis on 1 üür (<5) -> kasutatakse linnaosa Kristiine üüri: 6 kuulutust, mediaan 10 €/m²
    assert tondi["rent_level"] == "district"
    assert tondi["rent_estimate"] == pytest.approx(500)
    assert tondi["yield"] == pytest.approx(0.1)
    kr = listings[("Harjumaa", "Tallinn", "Kristiine", "Kristiine City")]
    assert kr["rent_level"] == "subdistrict"
    first = compute(s)["listings"][0]
    assert first["path"][-1] == "Tondi"  # sorditud tootluse järgi


def test_write_results(tmp_path):
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)], [mk(KR, 500) for _ in range(5)])
    out = tmp_path / "data" / "results.json"
    write_results(compute(s, generated_at="t"), out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["generated_at"] == "t"
    assert len(data["runs"]) == 1


def test_empty_store():
    res = compute(Store(":memory:"))
    assert res["regions"] == [] and res["listings"] == [] and res["runs"] == []
