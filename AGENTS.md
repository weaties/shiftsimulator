# AGENTS.md — shiftsim

Conventions for any AI coding agent working on shiftsim. Claude Code users: see
`CLAUDE.md` for the full model/architecture notes and project skills.

## Project overview

A sailing-tactics simulator for studying **when to tack or gybe** in different
wind shifts. You set up a wind scenario and a fleet of boats with different
decision strategies, race them on the same seeded wind, and compare who wins and
why (via ladder-rung gains). Python engine + a browser viewer.

**Stack:** Python 3.11+ standard library only (no third-party runtime deps — by
design). Charts are hand-written SVG; the interactive viewer is a static HTML
canvas fed by a stdlib HTTP server (`python -m shiftsim serve`).

## Essential commands

```bash
python tests/run_all.py                              # test suite (no pytest needed; pytest also works)
python -m shiftsim run scenarios/oscillating_demo.json --out out   # headless run
python -m shiftsim serve                             # interactive viewer
python -m shiftsim polar --max-speed 7.5             # inspect a synthetic polar
```

## Where things live

- `src/shiftsim/` — the engine (see the module map in `CLAUDE.md`)
- `web/` — `index.html` (interactive viewer), `docs.html` (model documentation)
- `scenarios/` — reproducible experiment configs
- `tests/` — `run_all.py` runner + `test_*.py`
- `docs/specs/` — design specs (write one before non-trivial features)

## Hard rules

1. **Keep docs in sync** with field/model changes (CLAUDE.md → "Keep the
   documentation in sync"). CI enforces that tooltip anchors resolve.
2. **No new runtime dependencies** without discussion.
3. **Determinism**: no unseeded randomness or wall-clock in the engine.
4. **Don't weaken the simulator's safety nets** to rescue a bad strategy.
5. Work through issues → (spec) → PR; never push to `main` directly.
