from tootlus.parser import Listing
from tootlus.store import Store


def L(id, price, area=50.0, rooms=2, location="Kesklinn, Tallinn"):
    return Listing(id, f"https://www.kv.ee/x-{id}", f"Tn 1, {location}", location, rooms, area, price, 1, 2000, "uus")


def test_repeat_listing_keeps_old_price():
    s = Store(":memory:")
    r1 = s.start_run("2026-01-01T00:00:00")
    s.save_listings(r1, 1, "Harjumaa", [L(1, 100000)])
    s.finish_run(r1, ["Harjumaa"], True)
    r2 = s.start_run("2027-01-01T00:00:00")
    s.save_listings(r2, 1, "Harjumaa", [L(1, 120000)])
    s.finish_run(r2, ["Harjumaa"], True)

    assert s.observations(r1)[0]["price"] == 100000
    assert s.observations(r2)[0]["price"] == 120000
    assert s.observations(r1)[0]["price_per_m2"] == 2000
    row = s.conn.execute("SELECT first_seen_run, last_seen_run FROM listings WHERE id=1").fetchone()
    assert tuple(row) == (r1, r2)


def test_observation_keeps_its_own_area_and_rooms():
    s = Store(":memory:")
    r1 = s.start_run()
    s.save_listings(r1, 2, "Harjumaa", [L(1, 500, area=50.0, rooms=2)])
    r2 = s.start_run()
    s.save_listings(r2, 2, "Harjumaa", [L(1, 500, area=40.0, rooms=1)])
    o1, o2 = s.observations(r1)[0], s.observations(r2)[0]
    assert (o1["area_m2"], o1["rooms"]) == (50.0, 2)
    assert (o2["area_m2"], o2["rooms"]) == (40.0, 1)
    assert s.conn.execute("SELECT area_m2 FROM listings WHERE id=1").fetchone()[0] == 40.0


def test_sale_and_rent_with_same_id_are_separate():
    s = Store(":memory:")
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [L(1, 100000)])
    s.save_listings(r, 2, "Harjumaa", [L(1, 500)])
    obs = sorted(s.observations(r), key=lambda o: o["deal_type"])
    assert [(o["deal_type"], o["price"]) for o in obs] == [(1, 100000), (2, 500)]


def test_missing_price_gives_null_price_per_m2():
    s = Store(":memory:")
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [L(1, None)])
    assert s.observations(r)[0]["price_per_m2"] is None


def test_runs_skips_empty_runs():
    s = Store(":memory:")
    r1 = s.start_run("2026-01-01T00:00:00")
    s.finish_run(r1, [], False)
    r2 = s.start_run("2026-02-01T00:00:00")
    s.finish_run(r2, ["Harjumaa", "Hiiumaa"], False)
    runs = s.runs()
    assert [r["id"] for r in runs] == [r2]
    assert runs[0]["counties_ok"] == ["Harjumaa", "Hiiumaa"]
    assert runs[0]["complete"] is False


def test_persists_to_file(tmp_path):
    path = tmp_path / "kv.sqlite"
    s = Store(str(path))
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [L(1, 100000)])
    s.finish_run(r, ["Harjumaa"], True)
    s.close()
    assert Store(str(path)).observations(r)[0]["price"] == 100000
