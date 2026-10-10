"""Local race server: Cadence brain on the left, arrow keys on the right.

Run:  .venv/bin/python server.py
Open: http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hall import Hall
from race import TICK_MS, Race

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
GAME = Race()
HALL = Hall(ROOT / "hall-of-fame.json")
LOCK = threading.Lock()


def public_state() -> dict:
    payload = GAME.snapshot()
    payload["hall"] = HALL.public()
    return payload


def _loop() -> None:
    interval = TICK_MS / 1000
    while True:
        started = time_monotonic()
        with LOCK:
            GAME.tick()
        remaining = interval - (time_monotonic() - started)
        if remaining > 0:
            threading.Event().wait(remaining)


def time_monotonic() -> float:
    import time

    return time.monotonic()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            with LOCK:
                payload = public_state()
            self._json(payload)
            return
        if path in {"/", "/index.html"}:
            self._file(STATIC / "index.html", "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            target = (STATIC / rel).resolve()
            if STATIC not in target.parents and target != STATIC:
                self.send_error(404)
                return
            kind = {
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".html": "text/html; charset=utf-8",
            }.get(target.suffix, "application/octet-stream")
            self._file(target, kind)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json({"ok": False, "error": "bad json"}, status=400)
            return
        with LOCK:
            if path == "/api/start":
                GAME.start()
            elif path == "/api/new":
                GAME.new_brain()
            elif path == "/api/hatch":
                GAME.hatch()
            elif path == "/api/pause":
                GAME.set_paused(bool(body.get("paused")))
            elif path == "/api/hold":
                direction = body.get("dir")
                GAME.hold(direction if isinstance(direction, str) else None)
            elif path == "/api/fame":
                if not GAME.fame_ready():
                    self._json({"ok": False, "error": "Finish every challenge with this brain first."}, status=400)
                    return
                try:
                    HALL.add(
                        str(body.get("name", "")),
                        level=GAME.level,
                        wins=GAME.scores["you"],
                        heats=GAME.heats,
                    )
                except ValueError as error:
                    self._json({"ok": False, "error": str(error)}, status=400)
                    return
                GAME.enshrine()
            else:
                self._json({"ok": False}, status=404)
                return
            payload = public_state()
        self._json({"ok": True, "state": payload})

    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    import os

    # Render and other hosts set PORT and require a public bind.
    # Locally, with no PORT, keep the server on this machine only.
    host = os.environ.get("HOST")
    if not host:
        host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    port = int(os.environ.get("PORT", "8765"))
    threading.Thread(target=_loop, daemon=True).start()
    server = ThreadingHTTPServer((host, port), Handler)
    shown = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    print(f"Cadence Brain Maze Run  http://{shown}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
