# Releases

Release notes for shiftsim. The `promote.yml` workflow (added with the
deployment feature) gates `main → stage → live` on a new `##` heading here.

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
