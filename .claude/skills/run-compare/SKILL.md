---
name: run-compare
description: Run a shiftsim scenario and compare boats/strategies — produce the comparison table, ladder-gain chart, tracks, and animated replay. Use when the user wants to run a matchup or interpret results.
---

# Run & compare a scenario

Read `CLAUDE.md` for what the metrics mean.

## Interactive viewer (recommended)

```bash
PYTHONPATH=src python3 -m shiftsim serve     # open http://localhost:8000/web/
```

Edit the wind pattern, course, and each boat (strategy + parameters + tack cost:
`tack time` and `recover speed×`) in the left panel, hit **Run**, and the Python
engine re-simulates and returns the replay. The viewer shows the animated course
with **rotating ladder rungs** + a ladder gauge (each boat's rung position now),
and a **per-maneuver calculation log** on the right — click a maneuver to jump
there and see the exact numbers (e.g. `advantage 8.2° > threshold 8.0° → tack`,
or `headed 6.1° ≥ trigger 6.0° → tack`, plus the metres lost to that tack).

## Run it headless

```bash
PYTHONPATH=src python3 -m shiftsim run scenarios/oscillating_demo.json --out out
```

Options: `--out DIR` (default `out`), `--step SEC` (override timestep),
`--quiet`. Writes to `DIR/`:
- `replay.json` — load in `web/index.html` for the animated top-down replay.
- `ladder_gain.svg` — each boat's ladder-rung gain vs the reference boat (boat 0)
  over time. The headline "who's winning, when, and by how much" chart.
- `tracks.svg` — top-down course with every boat's track.

To view the replay, serve the repo and open the page (the viewer auto-loads
`../out/replay.json` over http), or just open `web/index.html` and pick the
`replay.json` file:

```bash
python3 -m http.server -d . 8000   # then open http://localhost:8000/web/
```

## Read the table

```
 #  boat                     finish  tacks  gybes  dist(m)  up VMG   ladder
 1  Headers (tack on header)   1370s     11      9     2897    1.60       15
 ...
  Headers beats One-tack by 57s
```

- **finish** — elapsed time to round the last mark (`DNF` = didn't finish in
  `max_time`; treat as a red flag, see below).
- **tacks / gybes** — maneuver count; each one costs time, so this explains a lot.
- **dist** — metres sailed through the water (more = sailed a longer path).
- **up VMG** — average upwind velocity-made-good (m/s).
- **ladder** — final position up the wind axis.
- Boats are ranked best-first (finishers by time, then by ladder position).

## Interpreting / sanity checks

- **A `DNF` or a huge tack count** usually means a strategy is pathological, not
  that the boat is "slow". Check `n_struggled` (in `metrics.summarize`): if it's
  high, the thrash-breaker had to rescue the boat — the rule oscillates near
  laylines or fights the safety net. Fix the strategy (add hysteresis), don't
  loosen the safety nets.
- **For a fair A/B**, give the boats the *same polar* and only vary the strategy
  (or vice versa). All boats already see identical seeded wind.
- **Ladder-gain chart**: a gap that opens on a specific shift tells you exactly
  which decision paid off. The reference boat (index 0) is flat at zero by
  construction (`test_ref_boat_gain_is_zero`).

## Programmatic use

```python
from shiftsim.scenario import Scenario
from shiftsim.metrics import summarize, ladder_gain_series, rank
sc = Scenario.load("scenarios/oscillating_demo.json")
states = sc.run_sim()
for r in rank([summarize(b) for b in states]):
    print(r.name, r.finish_time)
```

## Done when
The table + charts answer the user's question (who wins and why), and any DNF
has been explained (pathological strategy) rather than left as a mystery.
