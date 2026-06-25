# shiftsim

A sailing tactics simulator for studying **when to tack or gybe in different
wind-shift situations**. Set up a wind scenario, put any number of boats on a
windward-leeward course with different polars and different decision strategies,
and compare the results — who reaches the mark first, and *why*.

It answers questions like: *In a 12° oscillation, does tacking on every header
really beat sailing straight? By how much? What about in a persistent shift?*

## Quick start

```bash
# run a scenario (pure Python, no install needed)
PYTHONPATH=src python3 -m shiftsim run scenarios/oscillating_demo.json --out out
```

```
 #  boat                     finish  tacks  gybes  dist(m)  up VMG   ladder
 1  Headers (tack on header)   1370s     11      9     2897    1.60       15
 2  One-tack (minimize tacks)  1427s      3      1     3158    1.48       15
 3  Lifts (control)            1452s      3      6     3177    1.49       13
  Headers beats One-tack by 57s
```

This writes `out/replay.json` (animated replay), `out/ladder_gain.svg` and
`out/tracks.svg`.

**Watch the replay:**
```bash
python3 -m http.server 8000      # then open http://localhost:8000/web/
```
…or open `web/index.html` and pick `out/replay.json`.

**Run the tests:** `python3 tests/run_all.py`

## What's modelled

- Boats sail at their **polar-optimal angle** off the wind and hold that TWA, so
  their heading rotates with the wind — that's what turns a shift into a lift or
  a header.
- **Wind scenarios:** steady, oscillating, persistent shift, puffs, and
  composites of these. Uniform in space today, structured so a spatial field
  drops in later.
- **Strategies** decide when to tack/gybe: `tack_on_header`, `minimize_tacks`
  (commit to a side), `tack_on_lift` (a control), `fixed_interval`. Pluggable —
  write your own.
- **Maneuver cost:** every tack/gybe loses time, so over-tacking is penalised.
- **Ladder-rung gain** vs a reference boat is the headline comparison metric.
- Fully **deterministic** from a scenario + seed, so two strategies face the
  identical wind.

No third-party dependencies — the engine is pure standard library; charts are
SVG and the replay is a static HTML canvas.

## Extending

The project ships Claude Code skills for the common tasks:
`add-wind-scenario`, `add-boat-strategy`, `run-compare`, `validate-physics`.
See [`CLAUDE.md`](CLAUDE.md) for architecture, conventions, and the model
details.

## Demos

- `scenarios/oscillating_demo.json` — tacking on the headers beats sailing
  straight; tacking on the lifts is worst.
- `scenarios/persistent_demo.json` — committing to the favoured side and
  minimising tacks beats both the wrong side and the over-tacker.
