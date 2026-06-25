---
name: add-boat-strategy
description: Add a new tack/gybe decision strategy or a new boat polar to shiftsim. Use when the user wants to model a new tactical rule (when to tack/gybe) or a new boat's performance.
---

# Add a boat / strategy

Two related tasks: **(A)** add a tack/gybe `Strategy`, or **(B)** add a boat polar.

Read `CLAUDE.md` first — especially the decision pipeline and conventions. The
key fact: a strategy only decides **whether to maneuver now**; the simulator
handles laylines, the maneuver cost, and the safety nets. So strategies stay
small and focused on the *tactic*.

## A. Add a Strategy

In `src/shiftsim/strategy.py`, subclass `Strategy`:

```python
class MyRule(Strategy):
    name = "my_rule"
    def __init__(self, threshold: float = 8.0):
        self.threshold = float(threshold)
    def reset(self):            # clear per-run state at the start of each run
        ...
    def decide(self, ctx: StrategyContext) -> bool:
        # return True to tack/gybe now
        ...
    def to_dict(self):
        return {"name": self.name, "threshold": self.threshold}
```

`StrategyContext` (read-only, given each step) has: `t, dt, point_of_sail`
(`"upwind"`/`"downwind"`), `tack`, `twd, tws, twa`, `heading_current`,
`heading_other`, `bearing_to_mark`, `dist_to_mark`, and `ctx.err(heading)` =
angular error of a heading vs the mark bearing (smaller = points closer).

Useful idioms (see existing presets):
- **Point-closest-to-mark** (the lifted tack): tack when
  `ctx.err(ctx.heading_other) < ctx.err(ctx.heading_current) - threshold`.
  This is `TackOnHeader`. The mirror is `TackOnLift` (a control that loses).
- **Keep your own state** across steps (e.g. a wind-direction EMA, a tack timer)
  on the instance; clear it in `reset()`. `FixedInterval` shows a simple timer.
- Branch on `ctx.point_of_sail` if upwind vs downwind logic should differ.

Also implement `explain(self, ctx) -> dict` (read-only; runs *after* `decide`
when a maneuver fires) returning the numbers behind the decision — this is what
the web viewer's per-maneuver calculation panel shows. Include a `"rule"` key and
the relevant values (thresholds, errors, the header amount, etc.).

Then:
1. Register in `_REGISTRY` at the bottom of the file (key = `name`).
2. Expose it in the web UI: add an entry to the `STRATS` map in
   `web/index.html` (`name: [[paramKey, label, default, docAnchor], ...]`) so it
   appears in the boat editor's strategy dropdown with the right parameter inputs.
2a. **Document it (required):** add a section + anchor for the strategy and each
   of its parameters in `web/docs.html`, and a `HELP` map entry in
   `web/index.html` for each new `data-help` key (short tooltip + `docs.html#anchor`).
   See "Keep the documentation in sync" in `CLAUDE.md`. Verify every tooltip
   anchor resolves with the `comm` check documented there.
3. Use it from a scenario: `"strategy": {"name": "my_rule", "threshold": 6}`.
4. Add a test in `tests/test_simulator.py` asserting the *expected tactical
   outcome* (e.g. it beats / loses to a baseline in a given wind). Run
   `python3 tests/run_all.py`.

**Sanity:** if your new strategy ever makes a boat DNF, check `n_struggled` in
the summary — a high value means it's thrashing and the thrash-breaker rescued
it. That usually means the rule oscillates; add hysteresis (a `threshold`) or a
minimum interval. A *good* strategy should rarely trigger the safety nets.

## B. Add a boat polar

A boat's speed model is a `Polar`. Three ways to provide one in a scenario's
`"polar"` block:
- **Synthetic:** `{"type":"synthetic","max_speed":7.5,"pointing":1.1,"light_air_factor":8}`
  — tune `max_speed` (top speed), `pointing` (>1 points higher / tighter upwind
  angle), `light_air_factor` (smaller = powers up sooner). Inspect with
  `python -m shiftsim polar --max-speed 7.5 --pointing 1.1`.
- **Real data:** `{"type":"csv","path":"path/to/polar.csv"}` — first row TWS,
  first column TWA, body = boat speed (knots). The common VPP/ORC export form.
- **Inline:** a full `{"twa":[...],"tws":[...],"table":[[...]]}` dict.

To give boats genuinely different behaviour for a comparison, vary `pointing`
and `max_speed`, or hand different boats different CSVs.

## Done when
- The strategy is registered, usable from a scenario, and has a test asserting
  its tactical outcome; **or** the polar loads and its `best_upwind`/
  `best_downwind` angles look realistic (≈30–55° upwind, ≈120–180° downwind).
