---
name: add-wind-scenario
description: Add a new wind model (oscillating/persistent/puff/spatial variant) or author a scenario JSON for shiftsim. Use when the user wants to model a new kind of wind shift or set up a new comparison scenario.
---

# Add a wind scenario

Two related tasks: **(A)** author a new scenario JSON (most common), or **(B)**
add a new `WindField` type to the engine.

Always read `CLAUDE.md` first for conventions (TWD = direction wind blows FROM,
bearings 0=N/90=E, seeded determinism).

## A. Author a scenario JSON

Scenarios live in `scenarios/*.json` and are the reproducible unit of an
experiment. Start from `scenarios/oscillating_demo.json` and edit. Schema:

```json
{
  "name": "...", "description": "...",
  "ref_twd": 0,                         // mean wind dir; the course/ladder axis
  "wind": { "type": "...", ... },       // see types below
  "course": { "type": "windward_leeward", "beat_length": 1200, "laps": 1 },
  "run": { "dt": 0.5, "max_time": 2400, "sample_every": 4 },
  "boats": [ { "name": "...", "color": "#1f77b4", "initial_tack": "starboard",
               "strategy": {...}, "polar": {...} } ]
}
```

Wind `type` values (params = the dataclass fields in `src/shiftsim/wind.py`):
- `steady` — `twd`, `tws`
- `oscillating` — `mean_twd`, `amplitude`, `period`, `phase`, `tws`
- `persistent` — `start_twd`, `total_shift`, `duration`, `tws`
- `puffy` — `base_twd`, `base_tws`, `gust_fraction`, `veer`, `seed`
- `composite` — `{ "type":"composite", "fields":[ ...wind dicts... ] }`
  (first field is the base; later ones layer their deviations + speed effect —
  e.g. a `persistent` base with an `oscillating` and a `puffy` on top)

Set `ref_twd` to the wind's mean direction so the course and ladder axis line up.
For a persistent shift, a reasonable `ref_twd` is the mean over the beat.

Then run it (see the `run-compare` skill) and eyeball `out/tracks.svg` to confirm
the boats sail a sensible course.

## B. Add a new WindField type

In `src/shiftsim/wind.py`:
1. Subclass `WindField`; implement `at(self, t, pos) -> (twd_deg, tws_kn)` and
   `to_dict`. Keep `at` pure and deterministic — if you need randomness, take a
   `seed` and build a `random.Random(seed)` in `__post_init__` (see `PuffyWind`).
   `pos` is available even for uniform fields so a **spatial** field (wind varying
   by position) can be added the same way — this is the intended extension point.
2. Add it to `_REGISTRY` and, if it has a nominal direction/speed, to
   `_nominal_twd` / `_nominal_tws` so it composes correctly.
3. Add a test in `tests/test_wind.py`: bounds/endpoints, `to_dict` round-trip,
   and (if seeded) determinism. Run `python3 tests/run_all.py`.

For a spatial field, also add a regression that two positions at the same `t`
differ, and confirm the simulator still runs (boats read wind at their own pos).

**Document any new field (required):** if the new wind type adds parameters that
surface in the web UI, add a section + anchor in `web/docs.html` and the matching
`data-help` key + `HELP` entry in `web/index.html`. See "Keep the documentation in
sync" in `CLAUDE.md`.

## Done when
- The scenario runs and the tracks look physically sensible, **or**
- the new field has a passing test and round-trips through `wind_from_dict`.
