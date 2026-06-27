# Spec: Deploy/admin status page

**Status:** Draft
**Risk Tier:** Elevated — adds **privileged actions** (deploy, service restart)
triggered from an **unauthenticated** web page on a crew-reachable box. See the
security section; this is an explicit, recorded owner decision.
**Related:** helmlog's `/admin/deployment` (`routes/admin.py`, `routes/deployment.py`,
`deploy.py`, `templates/admin/deployment.html`) — we mirror its information and
its action set (Deploy / Restart), but in pure stdlib. Issue #11. Builds on the
`/api/version` endpoint from #9.

---

## Problem

There's no way to see, from a browser, what's deployed on `corvopi-live` or to
push a new build without SSHing in. helmlog has a rich `/admin/deployment` page;
shiftsim should have the analogous thing.

## Security (read first)

shiftsim has **no auth**, and `/sim/` proxies straight to the app, so this page
and its `POST` endpoints are reachable by anyone on the boat LAN / crew tailnet.
The repo owner has **explicitly chosen to run it unauthenticated** after the
trade-off was raised. We bound the blast radius with **non-auth guardrails**:

1. **Trusted-branch allowlist.** `POST /api/admin/deploy` only accepts a branch in
   `{main, stage, live}` (default `live`). It can never check out an arbitrary,
   caller-supplied ref, so an unauthenticated caller can at worst redeploy/restart
   *already-trusted* code (a DoS-class nuisance), not run new code.
2. **Single-flight lock.** A `threading.Lock` (non-blocking acquire) rejects
   overlapping deploys with `409`, so two clicks can't race a checkout.
3. **No shell.** Every privileged call is an `argv` list to `subprocess.run`
   (no `shell=True`), with fixed arguments — nothing from the request is
   interpolated into a command except the validated branch name.

The docs page states plainly that the page is unauthenticated and what that means.

## Endpoints (added to `serve.py`)

All JSON, `Cache-Control: no-store`.

| Method + path | Purpose |
|---|---|
| `GET /api/admin/status` | `{running, track, commits_behind, restart_needed, service_active}` |
| `GET /api/admin/pipeline` | `{branches:{main,stage,live:{short_sha,message,timestamp}}, gaps:{main_ahead_of_stage, stage_ahead_of_live}}` |
| `GET /api/admin/promotions` | promotion history from `git tag -l 'stage/*' 'live/*' --sort=-creatordate` |
| `POST /api/admin/deploy` | `{branch?}` (allowlisted) → fetch + `reset --hard origin/<branch>` + restart |
| `POST /api/admin/restart` | restart the service |

- **`running`** reuses `version_info(dir)` from #9.
- **`commits_behind`** = `git rev-list --count HEAD..origin/<track>` after a fetch.
- **`restart_needed`** = the SHA on disk differs from the SHA the process started
  on (a deploy pulled code but the service hasn't restarted). The server records
  its startup SHA at import.
- **`service_active`** = `systemctl is-active shiftsim` (read-only; no sudo).
- **deploy/restart** shell out via a scoped `sudo` (see Pi-side). On a dev laptop
  (no sudoers, not the service user) they return a clear error — the page is for
  the deployed box; the read-only views work everywhere.

## Frontend `web/admin.html`

A standalone page (its own file, like `docs.html`), dark-themed to match,
mirroring helmlog's cards:

- **Current version** — running branch @ sha · clean/dirty, tracked branch,
  commits-behind, a status badge (Up to date / N behind / Restart needed), and
  **Deploy Now** + **Restart** buttons (each behind a `confirm()`).
- **Pipeline** — `main`/`stage`/`live` cards with sha + message + gap pills
  (green = up to date, amber/red = N ahead). Read-only.
- **Promotion history** — table from the promotion tags. Read-only.

JS uses **relative** API paths (`../api/admin/...`) so it works at `/web/admin.html`
and behind `/sim/web/admin.html`. Loads on open; after a deploy it waits for the
service to come back then reloads status. All server data HTML-escaped before
insertion. Reached via a small **"deploy status"** link added to the viewer footer
(`web/index.html`).

## Pi-side (privileged) — reproducible via `setup.sh`

`scripts/setup.sh` installs a scoped sudoers drop-in `/etc/sudoers.d/shiftsim`
(mirrors helmlog's `helmlog-allowed`), granting the `shiftsim` service user
exactly:

```sudoers
shiftsim ALL=(root) NOPASSWD: /usr/bin/systemctl restart shiftsim
shiftsim ALL=(root) NOPASSWD: /usr/bin/git -C /opt/shiftsim *
```

`git` runs as root because `/opt/shiftsim` is root-owned; `safe.directory` is
already passed by our git helper. `validate -f` gates the file before install.
No other privileges are added. Installing this needs the operator's sudo once
(re-running `setup.sh`).

## Constraints

- **Pure stdlib** — endpoints added to the existing `http.server` handler; no DB.
  Promotion history is read from git tags; there is **no** separate deploy-history
  store (the service's `ReadOnlyPaths` sandbox has nowhere persistent to write,
  and git already records the truth).
- Deterministic/boring: fixed argv, allowlisted inputs, read-only by default.

## Verification / test plan

- `test_admin.py` (no network/sudo):
  - branch allowlist: `_validate_track("live")` ok; `"main"`/`"stage"` ok;
    `"evil; rm -rf"` / `"origin/x"` / `""` rejected.
  - the deploy lock: second concurrent acquire fails fast.
  - `admin_status(dir)` shape on the repo checkout (keys present, types).
- Manual on the box: open `/sim/web/admin.html`, see the running build + pipeline;
  **Deploy Now** pulls `live` and restarts (page reflects new sha); **Restart**
  bounces the service.
- All four CI checks + the docs-anchor `comm` check pass.
