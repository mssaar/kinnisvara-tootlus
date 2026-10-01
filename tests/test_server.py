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


def post(url):
    req = urllib.request.Request(url, data=b"", method="POST")
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
