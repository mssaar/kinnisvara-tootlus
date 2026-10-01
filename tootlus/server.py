"""Kohalik veebiserver: serveerib docs/ kausta ja lubab kogumise uuesti käivitada."""
from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import pipeline
from .store import Store

MAX_MESSAGES = 50


class RunState:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.messages: list[str] = []
        self.error: str | None = None
        self.finished_at: str | None = None

    def _progress(self, message: str) -> None:
        with self._lock:
            self.messages = (self.messages + [message])[-MAX_MESSAGES:]

    def start(self, runner) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running, self.messages, self.error, self.finished_at = True, [], None, None
        threading.Thread(target=self._work, args=(runner,), daemon=True).start()
        return True

    def _work(self, runner) -> None:
        error = None
        try:
            runner(self._progress)
        except Exception as exc:  # noqa: BLE001 - kõik vead tuleb kasutajale näidata
            error = f"{type(exc).__name__}: {exc}"
        with self._lock:
            self.running, self.error = False, error
            self.finished_at = datetime.now().isoformat(timespec="seconds")

    def snapshot(self) -> dict:
        with self._lock:
            return {"running": self.running, "messages": list(self.messages),
                    "error": self.error, "finished_at": self.finished_at}


def _handler(state: RunState, runner):
    class Handler(SimpleHTTPRequestHandler):
        def _json(self, code: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?")[0] == "/api/status":
                return self._json(200, state.snapshot())
            return super().do_GET()

        def _same_origin(self) -> bool:
            # Kaitse teiste veebilehtede eest, mis võiksid kasutaja brauserist kogumise käivitada
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            return self.headers.get("Host") in hosts and (origin is None or origin in {f"http://{h}" for h in hosts})

        def do_POST(self):
            if self.path.split("?")[0] != "/api/run":
                return self._json(404, {"error": "not found"})
            if not self._same_origin():
                return self._json(403, {"error": "keelatud"})
            if state.start(runner):
                return self._json(202, {"started": True})
            return self._json(409, {"started": False, "error": "kogumine juba käib"})

        def end_headers(self):
            if not self.path.startswith("/api/"):
                self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, format, *args):
            pass

    return Handler


def make_server(port: int, docs_dir: Path, state: RunState, runner) -> ThreadingHTTPServer:
    handler = partial(_handler(state, runner), directory=str(docs_dir))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(port: int, counties: dict, browser: bool = False) -> None:
    def runner(progress):
        pipeline.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        store = Store(str(pipeline.DB_PATH))
        try:
            if browser:
                from .browser import collect_and_import
                collect_and_import(store, counties, progress=progress)
                pipeline.analyze_only(store, progress=progress)
            else:
                pipeline.run_once(store, counties=counties, progress=progress)
        finally:
            store.close()

    server = make_server(port, pipeline.ROOT / "docs", RunState(), runner)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Leht avatud: {url}  (Ctrl+C lõpetab)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
