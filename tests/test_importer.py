import shutil
from pathlib import Path

from tootlus import config
from tootlus.importer import import_dir, page_identity
from tootlus.store import Store

FIX = Path(__file__).parent / "fixtures"


def test_county_slug():
    assert config.county_slug("Harjumaa") == "harjumaa"
    assert config.county_slug("Ida-Virumaa") == "ida-virumaa"
    assert config.county_slug("Jõgevamaa") == "jogevamaa"
    assert config.county_slug("Lääne-Virumaa") == "laane-virumaa"
    assert config.county_slug("Võrumaa") == "vorumaa"


def test_page_identity_from_canonical_and_og_url():
    assert page_identity((FIX / "saved_sale.html").read_text(encoding="utf-8")) == (1, "Harjumaa")
    assert page_identity((FIX / "saved_rent.html").read_text(encoding="utf-8")) == (2, "Harjumaa")


def test_page_identity_unknown():
    assert page_identity("<html><head></head><body></body></html>") is None
    assert page_identity('<link rel="canonical" href="https://www.kv.ee/majad-muuk/harjumaa">') is None
    assert page_identity('<link rel="canonical" href="https://www.kv.ee/korterid-muuk/marsimaa">') is None


def test_import_dir_creates_run(tmp_path):
    shutil.copy(FIX / "saved_sale.html", tmp_path / "a.html")
    shutil.copy(FIX / "saved_sale.html", tmp_path / "a_duplicate.htm")
    shutil.copy(FIX / "saved_rent.html", tmp_path / "b.html")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "junk.html").write_text("<html>tühi</html>", encoding="utf-8")
    (tmp_path / "a_files").mkdir()
    messages = []
    s = Store(":memory:")
    ok = import_dir(s, tmp_path, progress=messages.append)
    assert ok == ["Harjumaa"]
    run = s.runs()[0]
    assert run["counties_ok"] == ["Harjumaa"]
    obs = s.observations(run["id"])
    assert sorted((o["deal_type"], o["id"]) for o in obs) == [(1, 1001), (1, 1002), (2, 2001)]
    assert any("junk.html" in m for m in messages)


def test_import_county_without_rent_is_skipped(tmp_path):
    shutil.copy(FIX / "saved_sale.html", tmp_path / "a.html")
    messages = []
    s = Store(":memory:")
    assert import_dir(s, tmp_path, progress=messages.append) == []
    assert s.runs() == []
    assert any("Harjumaa" in m and "üür" in m for m in messages)


def test_import_with_markers_only_imports_finished_counties(tmp_path):
    shutil.copy(FIX / "saved_sale.html", tmp_path / "harjumaa-muuk-00000.html")
    shutil.copy(FIX / "saved_rent.html", tmp_path / "harjumaa-uur-00000.html")
    (tmp_path / "hiiumaa.valmis").write_text("", encoding="utf-8")
    messages = []
    s = Store(":memory:")
    assert import_dir(s, tmp_path, progress=messages.append) == []
    assert s.runs() == []
    assert any("Harjumaa" in m and "pooleli, jäetakse välja" in m for m in messages)


def test_import_with_marker_imports_county(tmp_path):
    shutil.copy(FIX / "saved_sale.html", tmp_path / "harjumaa-muuk-00000.html")
    shutil.copy(FIX / "saved_rent.html", tmp_path / "harjumaa-uur-00000.html")
    (tmp_path / "harjumaa.valmis").write_text("", encoding="utf-8")
    s = Store(":memory:")
    assert import_dir(s, tmp_path, progress=lambda m: None) == ["Harjumaa"]
