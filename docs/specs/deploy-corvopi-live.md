# Spec: Deploy shiftsim to `corvopi-live` (nginx + systemd)

**Status:** Draft
**Risk Tier:** Standard — new ops scripts and a deployment surface; no change to
the simulation engine.
**Related:** helmlog deployment (`scripts/setup.sh`, `scripts/deploy.sh`,
`scripts/nginx/helmlog.conf`, `.github/workflows/promote.yml`) — we mirror its
technique.

---

## Problem

The simulator only runs on a developer's laptop today (`python -m shiftsim
serve`). The crew can't reach it. We want it permanently available in a browser
so anyone — coaches, helms, tacticians — can set up a wind scenario, race a few
strategies, and build intuition about when to tack or gybe. It should feel like
a hosted tool, not something you have to install.

## Solution

Run shiftsim as a long-lived **systemd service** on the Raspberry Pi
`corvopi-live`, bound to localhost (`127.0.0.1:8765`). Code is updated with a
`deploy.sh` that pulls `main` and restarts the service, and the box is
reproducible from an idempotent `setup.sh`. Reachable on the boat LAN by
hostname and over the crew Tailnet via Tailscale, with optional public HTTPS
later.

### Coexistence with helmlog (important)

`corvopi-live` **already runs helmlog behind nginx** on port 80, using helmlog's
single-port path-routing scheme (`/`, `/grafana/`, `/signalk/`, `/sk/`). shiftsim
must coexist, not compete. So:

- shiftsim ships **service-only** — `setup.sh` installs the systemd service and
  does **not** install or own nginx (that's a `--standalone-nginx` opt-in for a
  truly dedicated host).
- The reverse-proxy entry lives in **helmlog's** nginx config as one more path,
  `/sim/`, matching how `/grafana/` and `/signalk/` are done. This is a
  coordinated change in the helmlog repo (`scripts/nginx/helmlog.conf`), so it
  survives helmlog's `setup.sh` re-runs.
- The proxy **strips the `/sim/` prefix** (`proxy_pass http://shiftsim/;`), so the
  app serves at its own root internally and needs no base-path config. shiftsim
  is made **subpath-safe**: the bare root 302-redirects to `web/` (relative) and
  the viewer calls the API with a **relative** path (`../api/simulate`), so it
  works identically at `localhost:8000/web/` and at `corvopi-live/sim/web/`.

Crew URL: **`http://corvopi-live/sim/`**.

---

## Decision table: components

Each row is an independent piece of the implementation PR(s).

| Component | Artifact | Purpose |
|---|---|---|
| Service account | `shiftsim` system user (no login) | Run the app unprivileged, mirroring helmlog's `helmlog` account |
| Systemd unit | `scripts/systemd/shiftsim.service` | Supervise `python -m shiftsim serve`, restart on failure, start on boot |
| Reverse proxy | `scripts/nginx/shiftsim.conf` | nginx :80 → `127.0.0.1:8765`, single-port access |
| Provisioning | `scripts/setup.sh` | Idempotent: install nginx, create user, install unit + conf, enable + start. Re-runnable after a pull |
| Deploy | `scripts/deploy.sh` | `git pull` latest `main` (or a `--pr N` branch), restart the service |
| Input caps | engine guardrails in `serve.py` | `/api/simulate` runs user-supplied configs — bound them so a request can't wedge the Pi (see Security) |
| CI promotion | `.github/workflows/promote.yml` + `stage`/`live` branches | Gate `main → stage → live`, mirroring helmlog (optional Phase 2) |
| Crew access | Tailscale (Phase 1), Cloudflare Tunnel / Tailscale Funnel (Phase 2) | LAN + tailnet now; public HTTPS later |

## Architecture

```
            crew browser
                 │  http://corvopi-live/   (LAN or Tailscale MagicDNS)
                 ▼
        ┌───────────────────┐
        │ nginx :80         │  default_server, client_max_body_size small
        │  location /  ──────┼──► 127.0.0.1:8765
        └───────────────────┘
                 │
                 ▼
        ┌───────────────────┐
        │ shiftsim.service  │  python -m shiftsim serve --port 8765 --dir /opt/shiftsim
        │  User=shiftsim    │  binds 127.0.0.1 only (already the default)
        └───────────────────┘
                 │ serves web/ (index.html, docs.html) + POST /api/simulate
                 ▼
            the Python engine (pure stdlib)
```

The app already binds `127.0.0.1` in `serve.py`, so only nginx is exposed —
matching helmlog's loopback-service + nginx-front pattern.

## Concrete artifacts (proposed)

### `scripts/systemd/shiftsim.service`

```ini
[Unit]
Description=shiftsim sailing-tactics simulator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=shiftsim
WorkingDirectory=/opt/shiftsim
ExecStart=/usr/bin/python3 -m shiftsim serve --port 8765 --dir /opt/shiftsim
Environment=PYTHONPATH=/opt/shiftsim/src
Restart=always
RestartSec=2
# hardening (mirrors the spirit of helmlog's setup.sh)
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadOnlyPaths=/opt/shiftsim

[Install]
WantedBy=multi-user.target
```

### `scripts/nginx/shiftsim.conf`

```nginx
# shiftsim reverse proxy — single-port access on corvopi-live.
# Managed by setup.sh — do not edit directly on the Pi.
upstream shiftsim { server 127.0.0.1:8765; }

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # API requests are small JSON configs; keep the body cap tight.
    client_max_body_size 1m;

    location / {
        proxy_pass http://shiftsim;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # /api/simulate can run for a moment on a Pi; allow a little headroom.
    location /api/ {
        proxy_pass http://shiftsim;
        proxy_set_header Host $host;
        proxy_read_timeout 30s;
    }
}
```

### `scripts/setup.sh` (idempotent, sketch)

1. `apt-get install -y nginx git python3` (Pi OS already has python3).
2. Create the `shiftsim` system user if missing; clone/own `/opt/shiftsim`.
3. Install `shiftsim.service` to `/etc/systemd/system/`, `daemon-reload`,
   `enable --now`.
4. Install `shiftsim.conf` to `/etc/nginx/sites-available/`, symlink into
   `sites-enabled/`, remove the stock `default`, `nginx -t`, `reload`.
5. Scoped NOPASSWD sudo for exactly the systemctl/nginx commands `deploy.sh`
   needs (so deploys don't prompt), as helmlog does in `/etc/sudoers.d/`.

### `scripts/deploy.sh` (sketch)

Mirror helmlog: refuse to run as the wrong user, support `--pr N`, then
`git fetch && git checkout && git pull`, `sudo systemctl restart shiftsim`,
print the health-check URL. A pure-stdlib app means no dependency install step.

## Security

The one genuinely new exposure is **`POST /api/simulate` runs a user-supplied
scenario**. It's data-only (no code execution — it builds dataclasses), but an
adversarial or careless config could try to wedge the Pi. The implementation PR
must add input caps in `serve.py` / `Scenario.from_dict` before this is exposed:

- cap `run.max_time`, minimum `run.dt`, `course.laps`, and number of `boats`;
- reject configs whose `max_time / dt × boats` exceeds a step budget;
- keep the existing 1 MB body limit (already in `serve.py`) and nginx's cap.

Everything else is read-only and stateless — no accounts, no stored data, so no
data-licensing concerns. nginx is the only listening surface; the app stays on
loopback. Public exposure (Phase 2) goes through Tailscale Funnel / Cloudflare
Tunnel with HTTPS, same as helmlog — never a raw port-forward.

## Rollout

- **Phase 1 (this feature):** service + nginx + `setup.sh` + `deploy.sh` + input
  caps. Reachable at `http://corvopi-live/` on the LAN and over Tailscale. Done
  when a crew member on the tailnet can open it and run a comparison.
- **Phase 2 (follow-up issues):** `promote.yml` + `stage`/`live` branches for
  gated releases; public HTTPS via Tailscale Funnel or Cloudflare Tunnel;
  a `RELEASES.md`-gated promotion like helmlog.

## Verification / test plan

- `setup.sh` is idempotent: run twice on a fresh Pi, second run is a no-op.
- `systemctl status shiftsim` is active; survives `reboot`.
- `curl -s http://localhost:8765/web/` and `curl http://corvopi-live/` both 200.
- `POST /api/simulate` with a demo config returns a replay; an over-budget
  config is rejected with 400, not a hang.
- `deploy.sh` on a clean `main` pulls and restarts with no prompt.

### helmlog nginx addition (coordinated change)

Added to helmlog's `scripts/nginx/helmlog.conf`, alongside its other upstreams:

```nginx
upstream shiftsim { server 127.0.0.1:8765; }

# shiftsim sailing-tactics simulator — /sim/ (prefix stripped)
location = /sim  { return 301 /sim/; }
location /sim/ {
    proxy_pass http://shiftsim/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Open questions (resolved)

- **Port `8765`** — confirmed free on `corvopi-live`.
- **nginx ownership** — resolved: helmlog owns nginx; shiftsim is service-only
  and is proxied at `/sim/` (see Coexistence above).
- **Auto-deploy on merge** vs manual `deploy.sh` — staying manual for Phase 1,
  matching helmlog.
