"""A tiny stdlib dev server for the interactive web viewer.

Serves the static files (``web/``, ``out/``, ``scenarios/``) and exposes a single
JSON endpoint, ``POST /api/simulate``, which takes a scenario config (the same
shape as a ``scenarios/*.json`` file), runs the simulation, and returns the
replay data — including the per-maneuver calculation log.

Keeping the simulation in Python (not re-implemented in JS) means the web page
and the CLI always agree, and there's still nothing to install. Run it with:

    python -m shiftsim serve            # then open http://localhost:8000/web/
"""
from __future__ import annotations

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .report import replay_data
from .scenario import Scenario

MAX_BODY = 1 << 20  # 1 MB is plenty for a scenario config


class Handler(SimpleHTTPRequestHandler):
    def _send_json(self, code: int, obj: dict) -> None:
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/simulate":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                self._send_json(413, {"error": "config too large"})
                return
            cfg = json.loads(self.rfile.read(length) or b"{}")
            scenario = Scenario.from_dict(cfg)
            data = replay_data(scenario, scenario.run_sim())
            self._send_json(200, data)
        except Exception as e:  # noqa: BLE001  (report any config error to the UI)
            self._send_json(400, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *args) -> None:  # quieter console
        pass


def serve(directory: str, port: int = 8000) -> None:
    handler = partial(Handler, directory=directory)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"shiftsim serving {directory} at http://localhost:{port}/web/")
    print("POST /api/simulate to run a scenario.  Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
