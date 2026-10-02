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


def test_listing_attrs():
    s = Store(":memory:")
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [L(1, 100000)])
    s.save_listings(r, 2, "Harjumaa", [L(1, 500)])
    attrs = s.listing_attrs()
    assert attrs[(1, 1)] == {"floor": 1, "floors_total": None, "build_year": 2000, "condition": "uus"}
    assert set(attrs) == {(1, 1), (1, 2)}


def test_listing_attrs_include_floors_total():
    s = Store(":memory:")
    r = s.start_run()
    l = Listing(7, "u", "Tn 1, X", "X", 2, 50.0, 100000, 3, 2000, "uus", 9)
    s.save_listings(r, 1, "Harjumaa", [l])
    assert s.listing_attrs()[(7, 1)]["floors_total"] == 9


OLD_SCHEMA = """
CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
    complete INTEGER NOT NULL DEFAULT 0, counties_ok TEXT NOT NULL DEFAULT '');
CREATE TABLE listings (id INTEGER NOT NULL, deal_type INTEGER NOT NULL,
    url TEXT, address TEXT, location TEXT, county TEXT,
    rooms INTEGER, area_m2 REAL, floor INTEGER, build_year INTEGER, condition TEXT,
    first_seen_run INTEGER NOT NULL, last_seen_run INTEGER NOT NULL, PRIMARY KEY (id, deal_type));
INSERT INTO listings VALUES (5, 1, 'u', 'a', 'l', 'Harjumaa', 2, 50.0, 2, 1990, 'uus', 1, 1);
"""


def test_migrates_old_schema(tmp_path):
    import sqlite3
    path = tmp_path / "vana.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.commit()
    conn.close()
    s = Store(str(path))
    assert s.listing_attrs()[(5, 1)] == {"floor": 2, "floors_total": None, "build_year": 1990, "condition": "uus"}
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [Listing(6, "u", "a", "l", 1, 30.0, 1, 4, 2000, None, 5)])
    assert s.listing_attrs()[(6, 1)]["floors_total"] == 5
    s.close()
    Store(str(path)).close()  # teine avamine ei lisa veergu uuesti


def test_backfill_attrs_updates_only_existing():
    s = Store(":memory:")
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [Listing(1, "u", "a", "l", 2, 50.0, 100000, None, None, None)])
    s.finish_run(r, ["Harjumaa"], True)
    new = [Listing(1, "u2", "b", "m", 3, 60.0, 1, 4, 1985, "heas korras", 9),
           Listing(2, "u", "a", "l", 2, 50.0, 1, 1, 2000, None, 5)]
    assert s.backfill_attrs(1, new) == 1
    assert s.listing_attrs()[(1, 1)] == {"floor": 4, "floors_total": 9, "build_year": 1985, "condition": "heas korras"}
    assert (2, 1) not in s.listing_attrs()
    assert s.backfill_attrs(2, new) == 0
    assert len(s.runs()) == 1
    obs = s.observations(r)
    assert len(obs) == 1 and obs[0]["price"] == 100000 and obs[0]["rooms"] == 2


def test_backfill_keeps_existing_values_when_page_lacks_them():
    s = Store(":memory:")
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [Listing(1, "u", "a", "l", 2, 50.0, 1, 3, 1990, "heas korras", 5)])
    assert s.backfill_attrs(1, [Listing(1, "u", "a", "l", 2, 50.0, 1, None, None, None, 9)]) == 1
    assert s.listing_attrs()[(1, 1)] == {"floor": 3, "floors_total": 9, "build_year": 1990, "condition": "heas korras"}
