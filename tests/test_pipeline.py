import json

from tootlus import pipeline, scraper
from tootlus.geocode import Geocoder
from tootlus.parser import Listing
from tootlus.store import Store


def no_geo(store):
    return Geocoder(store.conn, fetch=lambda url: {"addresses": []}, sleep=lambda s: None)


def listings(location, price, n, start):
    return [Listing(start + i, f"u{start + i}", f"Tn, {location}", location, 2, 50.0, price, 1, 2000, None) for i in range(n)]


def test_run_once_saves_and_writes_results(tmp_path):
    def scrape(deal, county_id, on_page=None):
        if on_page:
            on_page(1, 5)
        if deal == 1:
            return listings("Kesklinn, Tallinn", 100000, 5, 0)
        return listings("Kesklinn, Tallinn", 500, 5, 100)

    out = tmp_path / "results.json"
    messages = []
    s = Store(":memory:")
    res = pipeline.run_once(s, counties={1: "Harjumaa"}, scrape=scrape, progress=messages.append, results_path=out,
                            model_path=tmp_path / "model.json", geocoder=no_geo(s))
    assert json.loads(out.read_text(encoding="utf-8"))["runs"][0]["counties_ok"] == ["Harjumaa"]
    assert any(r["level"] == "county" and r["enough"] for r in res["regions"])
    assert s.runs()[0]["complete"] is True
    assert any("Harjumaa" in m for m in messages)


def test_failed_county_is_skipped_but_others_kept(tmp_path):
    def scrape(deal, county_id, on_page=None):
        if county_id == 2 and deal == 2:
            raise scraper.FetchError("võrk maas")
        loc = "Kesklinn, Tallinn" if county_id == 1 else "Kärdla linn, Hiiumaa vald"
        return listings(loc, 100000 if deal == 1 else 500, 5, county_id * 1000 + deal * 100)

    s = Store(":memory:")
    messages = []
    res = pipeline.run_once(s, counties={1: "Harjumaa", 2: "Hiiumaa"}, scrape=scrape,
                            progress=messages.append, results_path=tmp_path / "r.json",
                            model_path=tmp_path / "model.json", geocoder=no_geo(s))
    run = s.runs()[0]
    assert run["counties_ok"] == ["Harjumaa"] and run["complete"] is False
    assert not [r for r in res["regions"] if r["path"][0] == "Hiiumaa"]
    # Hiiumaa müügid ei tohi andmebaasi jõuda ilma üürideta
    assert all(o["county"] == "Harjumaa" for o in s.observations(run["id"]))
    assert any("VIGA" in m and "Hiiumaa" in m for m in messages)


def test_analyze_only_writes_model_json(tmp_path):
    s = Store(":memory:")
    pipeline.analyze_only(s, tmp_path / "r.json", tmp_path / "m.json", no_geo(s), progress=lambda m: None)
    data = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert data["runs"] == [] and data["median"] is None


def test_publish_runs_git_commands(tmp_path):
    calls = []

    class Done:
        returncode = 0

    pipeline.publish(tmp_path, run=lambda args, cwd, check: calls.append(args) or Done())
    assert calls[0] == ["git", "add", "data", "docs/data"]
    assert calls[1][:3] == ["git", "commit", "-m"]
    assert calls[2] == ["git", "push"]


def test_collect_curl_with_no_counties_creates_no_run():
    def scrape(deal, county_id, on_page=None):
        raise scraper.FetchError("403")

    s = Store(":memory:")
    assert pipeline.collect_curl(s, counties={1: "Harjumaa"}, scrape=scrape, progress=lambda m: None) == []
    assert s.runs() == []


def test_collect_curl_returns_ok_counties():
    def scrape(deal, county_id, on_page=None):
        return listings("Kesklinn, Tallinn", 100000 if deal == 1 else 500, 5, deal * 100)

    s = Store(":memory:")
    assert pipeline.collect_curl(s, counties={1: "Harjumaa"}, scrape=scrape, progress=lambda m: None) == ["Harjumaa"]
    assert s.runs()[0]["counties_ok"] == ["Harjumaa"]
