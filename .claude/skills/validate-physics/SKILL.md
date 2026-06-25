---
name: validate-physics
description: Sanity-check the shiftsim physics/model after changes — run the regression suite and the known-result tactical checks so realism doesn't silently break. Use after editing the simulator, polar, wind, or strategy code.
---

# Validate the physics

Run after any change to `simulator.py`, `polar.py`, `wind.py`, `strategy.py`, or
the `RunConfig` knobs. The point is to catch *silent realism regressions* — code
that runs fine but no longer behaves like sailing.

## Run the suite

```bash
python3 tests/run_all.py        # no pytest needed; pytest also works
```

All tests must pass. The load-bearing ones:

| test | what it protects |
|---|---|
| `test_geometry.*` | angle conventions (TWD-from, bearings, heading = TWD±TWA) |
| `test_polar.best_upwind/downwind_angle_realistic` | optimal angles stay ≈30–55° up, ≈120–180° down |
| `test_physics.test_vmg_optimum_beats_neighbours` | chosen angle really maximises VMG |
| `test_physics.test_boat_sails_the_shift_keeps_twa` | boats hold TWA, heading rotates with the wind |
| `test_physics.test_extra_tacks_cost_distance` | maneuvers cost time/distance |
| `test_simulator.test_tack_on_header_beats_minimize_in_oscillation` | **the core result**: tacking on headers wins in oscillation |
| `test_simulator.test_favoured_side_wins_persistent` | committing to the favoured side wins a persistent shift |
| `test_simulator.test_determinism` | same scenario ⇒ identical result |
| `test_simulator.test_all_boats_finish_demos` | no livelock / divergence |

If you changed behaviour intentionally, update the test and say why in the diff —
don't delete a tactical regression to make red go green.

## Manual sanity checks (when adding to the model)

- **Optimal angles:** `python -m shiftsim polar` prints best upwind/downwind
  angles for a synthetic polar — they should look like a real boat.
- **Sailing the shift:** in a pure oscillation, a single `minimize_tacks` boat's
  heading should swing by the wind's amplitude while its TWA stays constant
  (that's `test_boat_sails_the_shift_keeps_twa`).
- **Tracks look right:** open `out/tracks.svg` — beats should zig-zag up toward
  the windward mark, runs fan down to the leeward mark; no boat should sail off
  to infinity or loop near a mark.
- **No spurious struggling:** check `n_struggled` for the *good* strategies
  (clean one-tack / well-tuned tack-on-header). It should be 0 or near 0. If a
  sensible strategy is being rescued by the thrash-breaker, the layline/EMA
  tuning regressed — investigate before shipping.

## Adding a new known-result test

When you add a wind type or strategy, add a test that asserts the *tactically
correct* outcome (who should win and why), not just "it runs". That's what keeps
the simulator trustworthy. Put physics invariants in `tests/test_physics.py` and
outcome checks in `tests/test_simulator.py`.

## Done when
`tests/run_all.py` is fully green, the core tactical results still hold, and any
intentional behaviour change is reflected in an updated test.
