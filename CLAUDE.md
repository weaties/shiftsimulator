# shiftsim — sailing tactics simulator

A simulator for studying **when to tack or gybe in different wind-shift
situations**. You set up a wind scenario (oscillating, persistent, puffy, or a
composite), put an arbitrary number of boats on the course with different polars
and different decision strategies, and compare what happens — who reaches the
mark first and *why*, measured in ladder-rung gains.

This file is the orientation for anyone (human or Claude) working in the repo.
Read it before making changes; it captures the conventions and the non-obvious
machinery that keeps results realistic.

## What it does / doesn't do

- **Does:** model boats sailing a windward-leeward course at polar-optimal angles,
  reacting to wind shifts, executing tack/gybe decisions from pluggable
  strategies, with a per-maneuver time cost; produce comparable metrics + an
  animated replay. Everything is deterministic given a scenario + seed.
- **Doesn't:** model boat-on-boat interaction, right-of-way, current, waves,
  crew work, or starts. It's a single-handed tactics sandbox, not a fleet sim.

## Running it

```bash
# interactive web viewer: edit wind/boats/tack-costs in the browser and re-run live
PYTHONPATH=src python3 -m shiftsim serve            # open http://localhost:8000/web/

# run a scenario headless: prints a comparison table, writes outputs to out/
PYTHONPATH=src python3 -m shiftsim run scenarios/oscillating_demo.json --out out

# dump a synthetic polar (and its optimal angles) to inspect/seed real data
PYTHONPATH=src python3 -m shiftsim polar --max-speed 7.5 --out mypolar.csv

# run the test suite (no pytest needed)
python3 tests/run_all.py
```

Outputs written to `--out`: `replay.json` (load it in `web/index.html` for the
animated top-down replay), `ladder_gain.svg`, `tracks.svg`.

**The interactive viewer (`serve`)** is the main way to explore. The browser
builds a scenario config from form controls (wind pattern, course, each boat's
strategy + parameters + tack cost) and POSTs it to `/api/simulate`; the Python
engine runs it and returns the replay. The simulation is **never** re-implemented
in JS — the page and the CLI always agree. The viewer shows the animated course,
**rotating ladder rungs** + a ladder gauge, and a **per-maneuver calculation
log** (the numbers behind every tack/gybe).

**No third-party dependencies — by design.** The engine is pure standard
library; charts are hand-written SVG and the replay is a static HTML canvas.
Keep it that way unless there's a strong reason; if you add an optional dep
(e.g. matplotlib), guard the import and degrade gracefully.

## Architecture (src/shiftsim/)

| module | responsibility |
|---|---|
| `geometry.py` | vectors + angle conventions. **All angle math goes through here.** |
| `polar.py` | `Polar` (speed vs TWA/TWS), `best_upwind`/`best_downwind`, synthetic generator, CSV import |
| `wind.py` | `WindField` base + `Steady`/`Oscillating`/`PersistentShift`/`Puffy`/`Composite`; `wind_from_dict` |
| `course.py` | `Mark`, `Course`, `windward_leeward()` builder |
| `boat.py` | `BoatConfig` (reusable), `BoatState` (per-run), `Sample` (one recorded instant) |
| `strategy.py` | `Strategy` base + presets; `StrategyContext`; `strategy_from_dict` |
| `simulator.py` | the step loop, laylines, maneuver cost, safety nets |
| `metrics.py` | `summarize`, `ladder_gain_series`, ranking |
| `scenario.py` | `Scenario` — loads a JSON experiment, runs it |
| `report.py` | text table, SVG charts, `replay.json` export (incl. maneuver log) |
| `serve.py` | stdlib dev server: static files + `POST /api/simulate` for the web UI |
| `cli.py` | `python -m shiftsim …` (`run` / `serve` / `polar`) |

## Conventions — get these right or everything drifts

- **Position** `(x, y)` in **metres**, x = East, y = North.
- **Bearings** in **degrees**, 0 = North, 90 = East, clockwise (nautical).
- **Wind direction (TWD)** = the direction the wind blows **FROM**. A Northerly
  is TWD 0. The windward mark lies in the `unit(TWD)` direction.
- **Speeds** in **knots** internally; converted to m/s only when integrating
  position (`KN_TO_MS` in `simulator.py`).
- **Heading from tack:** `heading = TWD ± TWA`, `+` = port (wind over the left),
  `−` = starboard. Same formula for beating (small TWA) and running (large TWA).
- Use `wrap360` / `wrap180` for every angle; never raw modulo at call sites.

## The physics model (and its assumptions)

- A boat sails at the **polar-optimal angle off the wind** for the current leg
  (`best_upwind` upwind, `best_downwind` downwind) and holds that TWA, so when
  the wind shifts its **heading rotates with the wind** — that's what makes a
  shift a lift or a header. (Regression test: `test_boat_sails_the_shift_keeps_twa`.)
- A **maneuver** (tack or gybe) costs time: for `maneuver_time` seconds the
  boat's speed is multiplied by a factor ramping from `maneuver_speed_factor`
  back to 1.0. This is the price every extra tack pays. Heading flips instantly
  (the lost distance of the turn is represented by the speed penalty).
- **Ladder rung** = projection of position onto the wind axis (`ref_twd`).
  Ladder-rung *gain* vs a reference boat is the headline comparison metric.

### Decision pipeline each step (simulator.step_boat)

Order matters. A maneuver happens if (subject to a debounce):
1. **Sailing-away safety** — heading > ~107° from the mark ⇒ force a maneuver and
   enter *recovery* (strategy suppressed until the next rounding). Guarantees a
   boat can never sail off the course to infinity.
2. **Fetch lock** — already laying the mark ⇒ never tack away from it.
3. **Near-mark zone** (`no_maneuver_radius`) ⇒ only laylines act, no tactics.
4. **Strategy** — `strategy.decide(ctx)` (the thing you're studying).
5. **Layline** — the other tack now fetches the mark ⇒ tack so you don't overstand.

Two safety nets keep *any* strategy (including bad/user ones) from breaking the
sim, while still letting it lose honestly:
- **Laylines use a smoothed wind estimate** (`_wind_ema`, `layline_wind_tau`),
  not the momentary direction — a tactician lays the mark on the average, so an
  oscillation near the layline doesn't blow the approach. This is why the EMA
  exists; don't replace it with instantaneous wind (boats then overstand and
  diverge — see git history / the comments).
- **Thrash-breaker** — if a boat maneuvers `thrash_limit` times within
  `thrash_window` seconds it's fighting the safety net (a pathological tactic);
  it's flagged "struggling" (`n_struggled`) and sailed on laylines until the next
  mark. It still finishes last, but it finishes.

**Closest-approach rounding:** a mark is rounded within its radius *or* on
closest approach within `capture_radius`, so a boat that passes near but not
exactly over the mark still rounds instead of sailing past into a dead end
(upwind, you can't beat back to a mark you've sailed past).

These knobs live in `RunConfig`. If you tune them, re-run `tests/run_all.py`:
the tactical regression tests (tack-on-header beats minimize in oscillation;
favoured side wins persistent) must still hold.

## Reproducibility

A scenario JSON + its seeds fully determines a run; all boats see the **same**
wind so comparisons are fair. `PuffyWind` is seeded. Don't introduce unseeded
randomness or wall-clock/`Math.random`-style nondeterminism — `test_determinism`
guards this.

## Extending — use the skills

- **`add-wind-scenario`** — add a new `WindField` or author a scenario JSON.
- **`add-boat-strategy`** — add a tack/gybe `Strategy` or a boat polar.
- **`run-compare`** — run a matchup and read the comparison output / replay.
- **`validate-physics`** — sanity-check the model after changes.

### Keep the documentation in sync (required)

`web/docs.html` is the model documentation — it explains how the simulator works
and what **every control-panel field** means, with anchored sections. Each field
in `web/index.html` carries a `data-help="<key>"` whose entry in the `HELP` map
(short tooltip + `docs.html#anchor`) points at the matching section.

Whenever you **add, remove, rename, or change the meaning of** a parameter, wind
model, strategy, metric, or RunConfig knob, you MUST in the same change:
1. update the relevant section (and its anchor) in `web/docs.html`;
2. update/add the field's `data-help` key, the `HELP` map entry, and (for a
   strategy parameter) the `STRATS` entry's doc anchor in `web/index.html`.

The tooltip anchors must all resolve — every `HELP[*].a` must be an `id=` in
`docs.html`. There's a quick check:

```bash
comm -23 <(grep -oE "a:'[a-z-]+'" web/index.html | sed "s/a:'//;s/'//" | sort -u) \
         <(grep -oE 'id="[a-z-]+"' web/docs.html | sed 's/id="//;s/"//' | sort)
# (prints nothing when every referenced anchor exists)
```

Treat a field whose behaviour the docs no longer describe as a bug, same as a
failing test.

---

Every maneuver is recorded with its reason and the numbers behind it
(`simulator._explain_maneuver` + each `Strategy.explain(ctx)`), exported in
`replay.json` and shown in the web viewer's calculation panel. When you add a
`Strategy`, also implement `explain(ctx)` (read-only — it runs *after* `decide`)
so its tacks are self-documenting; and expose any new strategy in the web UI's
`STRATS` map in `web/index.html`.

When you add a `WindField` or `Strategy`, register it (`wind_from_dict`'s
`_REGISTRY` / `strategy._REGISTRY`) and give it `to_dict` so scenarios stay
serialisable, then add a test. Match the surrounding style: dataclasses,
docstrings that explain the *sailing* meaning, no new dependencies.
