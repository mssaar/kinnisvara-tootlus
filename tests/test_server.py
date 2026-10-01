import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from tootlus.server import RunState, make_server


@pytest.fixture
def server(tmp_path):
    (tmp_path / "index.html").write_text("<h1>tere</h1>", encoding="utf-8")
    gate = threading.Event()

    def runner(progress):
        progress("Harjumaa müük: leht 1")
        gate.wait(5)

    state = RunState()
    srv = make_server(0, tmp_path, state, runner)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", gate, state
    gate.set()
    srv.shutdown()


def get_json(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def post(url, headers=None):
    req = urllib.request.Request(url, data=b"", method="POST", headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def wait_until(pred, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_serves_static_files(server):
    base, _, _ = server
    with urllib.request.urlopen(base + "/") as r:
        assert b"tere" in r.read()


def test_run_lifecycle(server):
    base, gate, _ = server
    assert get_json(base + "/api/status")["running"] is False
    assert post(base + "/api/run") == 202
    assert wait_until(lambda: get_json(base + "/api/status")["messages"] == ["Harjumaa müük: leht 1"])
    assert get_json(base + "/api/status")["running"] is True
    assert post(base + "/api/run") == 409
    gate.set()
    assert wait_until(lambda: get_json(base + "/api/status")["running"] is False)
    status = get_json(base + "/api/status")
    assert status["error"] is None and status["finished_at"]


def test_runner_error_is_reported():
    state = RunState()

    def boom(progress):
        raise RuntimeError("katki")

    assert state.start(boom)
    assert wait_until(lambda: not state.snapshot()["running"])
    assert "katki" in state.snapshot()["error"]


def test_run_rejects_foreign_origin(server):
    base, _, state = server
    assert post(base + "/api/run", {"Origin": "https://kuri.example"}) == 403
    assert post(base + "/api/run", {"Origin": "null"}) == 403
    assert state.snapshot()["running"] is False and state.snapshot()["finished_at"] is None


def test_run_rejects_foreign_host(server):
    base, _, state = server
    port = base.rsplit(":", 1)[1]
    assert post(base + "/api/run", {"Host": f"kuri.example:{port}"}) == 403
    assert post(base + "/api/run", {"Host": "127.0.0.1:1"}) == 403
    assert state.snapshot()["running"] is False


def test_run_accepts_own_origin(server):
    base, _, _ = server
    port = base.rsplit(":", 1)[1]
    assert post(base + "/api/run", {"Origin": f"http://localhost:{port}", "Host": f"localhost:{port}"}) == 202


def test_nothing_collected_sets_plain_error():
    from tootlus.server import NothingCollected
    state = RunState()

    def runner(progress):
        raise NothingCollected("Ühtegi maakonda ei kogutud")

    assert state.start(runner)
    assert wait_until(lambda: not state.snapshot()["running"])
    assert state.snapshot()["error"] == "Ühtegi maakonda ei kogutud"


def _patch_runner_env(monkeypatch, tmp_path, ok):
    from tootlus import browser, pipeline
    calls = []
    monkeypatch.setattr(pipeline, "DB_PATH", tmp_path / "kv.sqlite")
    monkeypatch.setattr(browser, "collect_and_import", lambda store, counties, progress: calls.append("browser") or ok)
    monkeypatch.setattr(pipeline, "collect_curl", lambda store, counties, progress: calls.append("curl") or ok)
    monkeypatch.setattr(pipeline, "analyze_only", lambda store, progress: calls.append("analyze"))
    return calls


def test_runner_defaults_to_browser_and_fails_on_nothing(monkeypatch, tmp_path):
    from tootlus.server import NothingCollected, make_runner
    calls = _patch_runner_env(monkeypatch, tmp_path, [])
    with pytest.raises(NothingCollected, match="Ühtegi maakonda ei kogutud"):
        make_runner({1: "Harjumaa"})(lambda m: None)
    assert calls == ["browser"]


def test_runner_curl_mode_analyzes_on_success(monkeypatch, tmp_path):
    from tootlus.server import make_runner
    calls = _patch_runner_env(monkeypatch, tmp_path, ["Harjumaa"])
    make_runner({1: "Harjumaa"}, curl=True)(lambda m: None)
    assert calls == ["curl", "analyze"]
