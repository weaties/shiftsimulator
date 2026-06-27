# Releases

Release notes for shiftsim. The `promote.yml` workflow gates `main → stage`
on a new `##` heading here (commit sets that only touch `docs/roadmap.md` are
exempt). `stage → live` has no gate.

## 0.4.0 — In-app feedback footer (version stamp + bug/feature links)

- New read-only `GET /api/version` endpoint reports the running build
  (`hostname`, `branch`, `sha`, `dirty`) from git — sandbox-safe
  (`safe.directory` + `--no-optional-locks`, degrades to `"unknown"` rather than
  erroring outside a checkout).
- The viewer gains a **footer** showing `host · branch @ commit · clean/dirty`,
  plus **Report a bug** / **Request a feature** links that deep-link to GitHub's
  pre-filled issue form (client-side, no server token, labelled `from-app`).
- Bug reports **embed the current scenario JSON**, so every report reproduces the
  run 1:1 — the project's determinism ethos.
- Docs: new `web/docs.html#feedback` section + matching tooltip/anchor. Mirrors
  helmlog's feedback-footer pattern. Closes #9.

## 0.3.0 — Release-promotion gate + parity with helmlog

- `.github/workflows/promote.yml` — manual, fast-forward-only promotion of
  `main → stage → live` with dated tags and a rollback path, mirroring helmlog.
  Promoting to `stage` requires a new `##` entry in this file.
- `stage` and `live` deployment branches created off `main`.
- Agent docs and dev toolchain brought to parity with helmlog (single canonical
  `AGENTS.md` imported by `CLAUDE.md`; `uv` dev toolchain; ruff + mypy; CI lint
  job). See the parity PR for detail.

## 0.2.0 — Deploy to corvopi-live (#1)

Phase 1 of getting the simulator in front of the crew.

- `scripts/setup.sh` — idempotent provisioning: nginx, a `shiftsim` service
  account, and a hardened systemd service running `python -m shiftsim serve` on
  localhost, fronted by nginx on port 80 (mirrors helmlog's deploy technique).
- `scripts/deploy.sh` — pull `main` (or `--pr N`) and restart the service.
- `scripts/systemd/shiftsim.service`, `scripts/nginx/shiftsim.conf` — reference
  artifacts; the bare host redirects to `/web/`.
- Compute caps on the public `POST /api/simulate` (`shiftsim.serve.validate_request`):
  bounds on boats, dt, max_time, laps, and a step-boat budget, so an adversarial
  config can't wedge the Pi. Over-limit requests return `413` with a clear reason.
- **Coexists with helmlog on `corvopi-live`:** ships service-only (no competing
  nginx); proxied at `/sim/` by helmlog's nginx. App is subpath-safe — bare root
  redirects to `web/` (relative) and the viewer calls the API relatively
  (`../api/simulate`), so it works at both `localhost:8000/web/` and
  `corvopi-live/sim/web/`. `setup.sh --standalone-nginx` remains for a dedicated host.

## 0.1.0 — Initial release

The first working version of the sailing-tactics simulator.

- Pure-stdlib simulation engine: polar-curve boats, windward-leeward course,
  per-maneuver time cost, seeded determinism.
- Wind models: steady, oscillating, persistent shift, puffs, and composites.
- Strategies: `minimize_tacks`, `tack_on_header`, `tack_on_lift` (control),
  `tack_at_half_header`, `fixed_interval` — headers measured from the wind
  (not the bearing to the mark), so steady wind produces no spurious tacks.
- Robust laylines (mean-wind estimate), fetch lock, sailing-away catch,
  thrash-breaker, and closest-approach rounding.
- Metrics: ladder-rung gain, VMG, finish time; SVG charts.
- Interactive web viewer: editable wind / boats / tack-cost, animated replay
  with rotating ladder rungs and a ladder gauge, and a per-maneuver calculation
  log served by a stdlib HTTP API (`python -m shiftsim serve`).
- Model documentation (`web/docs.html`) with per-field help; CI guards that the
  docs stay in sync with the UI.
- Project skills: `add-wind-scenario`, `add-boat-strategy`, `run-compare`,
  `validate-physics`.
