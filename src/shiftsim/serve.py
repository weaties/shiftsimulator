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

# Caps for the public /api/simulate endpoint. The simulation is data-only (no
# code execution), but it runs on a Raspberry Pi, so an adversarial or careless
# config must not be able to wedge it. These bound the worst-case compute; the
# defaults a real user picks are orders of magnitude under them.
LIMITS = {
    "max_boats": 16,
    "min_dt": 0.2,          # s — finer timesteps multiply the work
    "max_time": 7200.0,     # s — simulated seconds
    "max_laps": 12,
    "max_step_boats": 500_000,   # (max_time / dt) * boats — the real work budget.
                                 # Reasonable runs are far under (3 boats × 3000s/0.5 ≈ 18k);
                                 # this only catches pathological many-boats × long × fine-dt combos.
}


class RequestTooLarge(ValueError):
    """Raised when a scenario config exceeds the API compute limits."""


def validate_request(cfg: dict) -> None:
    """Reject configs that would cost too much to simulate. Raises
    :class:`RequestTooLarge` with a human-readable reason, or returns None."""
    boats = cfg.get("boats") or []
    n = len(boats)
    if n < 1:
        raise RequestTooLarge("at least one boat is required")
    if n > LIMITS["max_boats"]:
        raise RequestTooLarge(f"too many boats ({n} > {LIMITS['max_boats']})")

    run = cfg.get("run") or {}
    dt = float(run.get("dt", 0.5))
    max_time = float(run.get("max_time", 3600.0))
    laps = int((cfg.get("course") or {}).get("laps", 1))

    if dt < LIMITS["min_dt"]:
        raise RequestTooLarge(f"dt too small ({dt} < {LIMITS['min_dt']}s)")
    if max_time > LIMITS["max_time"]:
        raise RequestTooLarge(f"max_time too large ({max_time} > {LIMITS['max_time']}s)")
    if laps > LIMITS["max_laps"]:
        raise RequestTooLarge(f"too many laps ({laps} > {LIMITS['max_laps']})")

    budget = (max_time / max(dt, 1e-9)) * n
    if budget > LIMITS["max_step_boats"]:
        raise RequestTooLarge(
            f"work budget exceeded ({int(budget):,} step-boats > "
            f"{LIMITS['max_step_boats']:,}); reduce max_time, raise dt, or use fewer boats")


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
            validate_request(cfg)
            scenario = Scenario.from_dict(cfg)
            data = replay_data(scenario, scenario.run_sim())
            self._send_json(200, data)
        except RequestTooLarge as e:
            self._send_json(413, {"error": str(e)})
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
