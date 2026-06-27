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

import contextlib
import json
import socket
import subprocess
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import admin
from .report import replay_data
from .scenario import Scenario

MAX_BODY = 1 << 20  # 1 MB is plenty for a scenario config

# Caps for the public /api/simulate endpoint. The simulation is data-only (no
# code execution), but it runs on a Raspberry Pi, so an adversarial or careless
# config must not be able to wedge it. These bound the worst-case compute; the
# defaults a real user picks are orders of magnitude under them.
LIMITS = {
    "max_boats": 16,
    "min_dt": 0.2,  # s — finer timesteps multiply the work
    "max_time": 7200.0,  # s — simulated seconds
    "max_laps": 12,
    "max_step_boats": 500_000,  # (max_time / dt) * boats — the real work budget.
    # Reasonable runs are far under (3 boats × 3000s/0.5 ≈ 18k);
    # this only catches pathological many-boats × long × fine-dt combos.
}


@lru_cache(maxsize=8)
def version_info(directory: str) -> dict:
    """Return the running build as ``{hostname, branch, sha, dirty}``.

    Read from git on ``directory`` (the served repo). Invoked with
    ``safe.directory`` + ``--no-optional-locks`` so it works under the deployed
    service's sandbox (``ReadOnlyPaths=/opt/shiftsim``) and on a **root-owned**
    checkout served by the unprivileged ``shiftsim`` user — git would otherwise
    refuse with "dubious ownership". A tree with uncommitted changes *or* commits
    ahead of its upstream reads as ``dirty`` (a hand-edited / un-deployed box).

    Any failure (not a checkout, no git, timeout) degrades to ``"unknown"``
    rather than raising: the ``/api/version`` endpoint must never 500 the viewer.
    Cached so git runs once per directory in the long-lived server.
    """
    hostname = socket.gethostname()
    base = ["git", "-C", directory, "-c", f"safe.directory={directory}", "--no-optional-locks"]

    def _git(*args: str) -> str:
        out = subprocess.run(
            base + list(args), capture_output=True, text=True, timeout=5, check=True
        )
        return out.stdout.strip()

    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
        sha = _git("rev-parse", "--short", "HEAD") or "unknown"
        dirty = bool(_git("status", "--porcelain"))
        if not dirty:
            # No upstream tracked (e.g. a detached deploy) — treat as clean.
            with contextlib.suppress(Exception):
                dirty = int(_git("rev-list", "@{upstream}..HEAD", "--count")) > 0
    except Exception:  # noqa: BLE001 — not a checkout / no git / timeout
        return {"hostname": hostname, "branch": "unknown", "sha": "unknown", "dirty": False}
    return {"hostname": hostname, "branch": branch, "sha": sha, "dirty": dirty}


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
            f"{LIMITS['max_step_boats']:,}); reduce max_time, raise dt, or use fewer boats"
        )


class Handler(SimpleHTTPRequestHandler):
    def _send_json(self, code: int, obj: dict) -> None:
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        # Send the bare root to the viewer. A *relative* redirect so it works
        # both at the host root (-> /web/) and behind a proxy subpath that
        # strips its prefix (e.g. /sim/ -> app / -> browser /sim/web/).
        path = urlparse(self.path).path
        if path in ("", "/"):
            self.send_response(302)
            self.send_header("Location", "web/")
            self.end_headers()
            return
        # The build stamp shown in the viewer footer (and used to tag bug reports).
        if path == "/api/version":
            self._send_json(200, version_info(self.directory))
            return
        # Read-only deployment views for web/admin.html.
        if path == "/api/admin/status":
            self._admin_get(admin.status)
            return
        if path == "/api/admin/pipeline":
            self._admin_get(admin.pipeline)
            return
        if path == "/api/admin/promotions":
            self._admin_get(admin.promotions)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/simulate":
            self._simulate()
            return
        # Deployment actions for web/admin.html. UNAUTHENTICATED by design (see
        # admin.py / docs/specs/admin-page.md); bounded by the trusted-branch
        # allowlist and the single-flight lock inside admin.deploy.
        if path == "/api/admin/deploy":
            self._admin_deploy()
            return
        if path == "/api/admin/restart":
            self._admin_action(admin.restart)
            return
        self.send_error(404)

    def _simulate(self) -> None:
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

    def _admin_get(self, fn: object) -> None:
        try:
            self._send_json(200, fn(self.directory))  # type: ignore[operator]
        except Exception as e:  # noqa: BLE001 — report read failures to the page
            self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def _admin_deploy(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if 0 < length <= MAX_BODY else b""
            branch = (json.loads(body or b"{}") or {}).get("branch", admin.TRACK_DEFAULT)
            self._send_json(200, admin.deploy(self.directory, branch))
        except admin.AdminError as e:
            code = 409 if "in progress" in str(e) else 400
            self._send_json(code, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def _admin_action(self, fn: object) -> None:
        try:
            self._send_json(200, fn())  # type: ignore[operator]
        except admin.AdminError as e:
            self._send_json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *args: object) -> None:  # quieter console
        pass


def serve(directory: str, port: int = 8000) -> None:
    admin.record_startup(directory)  # snapshot the deployed SHA for "restart needed"
    handler = partial(Handler, directory=directory)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"shiftsim serving {directory} at http://localhost:{port}/web/")
    print("POST /api/simulate to run a scenario.  Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
