import pytest

import run
from tootlus import browser, pipeline


@pytest.fixture
def env(monkeypatch, tmp_path):
    calls = []
    result = {"ok": ["Harjumaa"]}
    monkeypatch.setattr(pipeline, "DB_PATH", tmp_path / "kv.sqlite")
    monkeypatch.setattr(browser, "collect_and_import",
                        lambda store, counties, **kw: calls.append(("browser", sorted(counties))) or result["ok"])
    monkeypatch.setattr(pipeline, "collect_curl",
                        lambda store, counties, **kw: calls.append(("curl", sorted(counties))) or result["ok"])
    monkeypatch.setattr(pipeline, "analyze_only",
                        lambda store, **kw: calls.append(("analyze",)) or {"regions": [], "listings": []})
    monkeypatch.setattr(pipeline, "publish", lambda root: calls.append(("publish",)))
    return calls, result


def test_default_mode_is_browser(env):
    calls, _ = env
    assert run.main(["--counties", "1"]) == 0
    assert calls == [("browser", [1]), ("analyze",)]


def test_browser_flag_is_accepted_alias(env):
    calls, _ = env
    assert run.main(["--browser"]) == 0
    assert calls[0][0] == "browser"


def test_curl_flag(env):
    calls, _ = env
    assert run.main(["--curl", "--counties", "2"]) == 0
    assert calls == [("curl", [2]), ("analyze",)]


@pytest.mark.parametrize("argv", [[], ["--curl"], ["--publish"]])
def test_nothing_collected_exits_1_without_analysis(env, capsys, argv):
    calls, result = env
    result["ok"] = []
    assert run.main(argv) == 1
    assert ("analyze",) not in calls and ("publish",) not in calls
    assert "Ühtegi maakonda ei kogutud" in capsys.readouterr().err


def test_empty_import_dir_exits_1(env, tmp_path, capsys):
    calls, _ = env
    folder = tmp_path / "tühi"
    folder.mkdir()
    assert run.main(["--import-dir", str(folder)]) == 1
    assert ("analyze",) not in calls
    assert "Ühtegi maakonda ei kogutud" in capsys.readouterr().err


def test_analyze_only_does_not_collect(env):
    calls, _ = env
    assert run.main(["--analyze-only"]) == 0
    assert calls == [("analyze",)]


def test_backfill_dir_flag(env, monkeypatch, tmp_path):
    from tootlus import importer
    calls, _ = env
    seen = []
    monkeypatch.setattr(importer, "backfill_dir", lambda store, directory, **kw: seen.append(str(directory)) or 3)
    assert run.main(["--backfill-dir", str(tmp_path)]) == 0
    assert seen == [str(tmp_path)]
    assert calls == []  # ei kogu ega analüüsi
