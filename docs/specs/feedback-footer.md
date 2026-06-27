# Spec: In-app feedback footer (version stamp + bug/feature links)

**Status:** Draft
**Risk Tier:** Standard — a new read-only API endpoint and a UI footer; no change
to the simulation engine, no new secret on the box.
**Related:** helmlog's feedback footer (`templates/base.html`, `static/shared.js`,
`routes/_helpers.py`) — we mirror its technique. Issue #9.

---

## Problem

shiftsim is deployed for the crew at `corvopi-live/sim/`, but a user in the
browser can't tell **which build** they're looking at, and has **no way to report
a bug or request a feature**. When someone hits an odd result we get no
reproducible report and nothing to tie it to a commit.

## Solution

Add an **in-app feedback footer**, mirroring helmlog's pattern: a small footer on
the viewer page that shows the running build and offers "Report a bug" /
"Request a feature" links. The links **deep-link to GitHub's pre-filled
`issues/new` form** — entirely client-side, so there is **no server-side GitHub
token and no new backend write surface**. Users file via their own GitHub login,
exactly as in helmlog.

Three pieces:

### 1. Version endpoint — `GET /api/version`

A new read-only endpoint in `serve.py` returns the running build as JSON:

```json
{"hostname": "corvopi-live", "branch": "live", "sha": "c0aaa27", "dirty": false}
```

- Computed at runtime from git, on the directory the server serves (`--dir`),
  cached with `functools.lru_cache` so git runs once per process.
- Invoked as `git -c safe.directory=<dir> --no-optional-locks <cmd>` so it works
  under the systemd sandbox (`ReadOnlyPaths=/opt/shiftsim`) and despite the repo
  being **root-owned** while the service runs as the `shiftsim` user (git would
  otherwise refuse with "dubious ownership").
- `dirty` = `git status --porcelain` non-empty **or** commits ahead of upstream
  (mirrors helmlog: a deployed tree that's been hand-edited or is ahead of
  `origin` reads as dirty).
- **Degrades gracefully:** any git failure (not a checkout, no git binary)
  returns the dict with `branch`/`sha` = `"unknown"`, `dirty` = `false` — never
  raises, never 500s.

Response carries `Cache-Control: no-store` (reuses `_send_json`).

### 2. Footer in `web/index.html`

A `<footer id="foot">` after the right panel, fetched on page load:

```
corvopi-live · live @ c0aaa27 · clean   ·   Report a bug   ·   Request a feature
```

- On `load`, `fetch('../api/version')` (relative, so it works at `/web/` and at
  `/sim/web/`) populates the version span.
- `buildIssueUrl(kind)` builds a GitHub `issues/new` URL with a pre-filled title,
  body, and labels, opened in a new tab. Collected context:
  - **kind = bug:** Description / Steps / Expected-vs-actual sections, then a
    metadata table (page URL, version, browser, screen, timestamp) **and a fenced
    `json` block containing the current scenario config** (`buildConfig()`), so the
    report is reproducible 1:1. Labels: `from-app,bug`.
  - **kind = feature:** Description / Use-case sections + metadata table.
    Labels: `from-app,enhancement`.
- Config is URL-encoded; typical configs are < 2 KB, well within practical URL
  limits. If GitHub truncates an unusually large URL the user still gets a
  pre-filled form — no data loss in the app.

### 3. GitHub issue templates

`.github/ISSUE_TEMPLATE/`:
- `bug_report.yml` — What happened / Expected / **Scenario JSON** (paste) /
  Environment / Version. Labels `from-app,bug` (default-applied).
- `feature_request.yml` — Use case / Proposed behaviour / Scope.
- `config.yml` — allow blank issues; link to the docs.

## Decision: no server-side issue creation

Rejected a `POST /api/issue` that creates issues via a stored token. It would put
a write-scoped GitHub token on a public-facing Pi and need rate-limiting/abuse
handling. The deep-link approach has none of that exposure and matches helmlog.
Trade-off: a user without a GitHub account can't file — acceptable for a crew tool.

## Docs

`web/docs.html` gains a `#feedback` section explaining the footer (version stamp
meaning + how the report links work). The footer carries `data-help="feedback"`,
with a matching `HELP['feedback'] = {a:'feedback', t:'…'}` entry in
`web/index.html`, so the docs-in-sync CI check passes.

## Verification / test plan

- `test_version.py`: `version_info(<repo>)` returns a dict with the four keys,
  `sha`/`branch` are non-empty strings in a real checkout; `version_info(<non-git
  dir>)` returns the graceful fallback without raising.
- Manual: load the viewer, footer shows the build; "Report a bug" opens a GitHub
  form pre-filled with the current scenario JSON; "Request a feature" opens the
  feature form.
- All four CI checks (tests, ruff check, ruff format, mypy) + the docs-anchor
  `comm` check pass.
