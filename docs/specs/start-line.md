# Spec: Start-line situation simulator (named boats, bad-air model + viz)

**Status:** Draft
**Risk Tier:** Elevated — first **boat-on-boat interaction** in the engine (the
bad-air wind shadow). Touches the simulator step loop and the determinism
guarantee, so it lands behind a default-**off** flag and with an order-independent
two-phase step that `test_determinism` continues to guard.
**Related:** Issue #13. Follows the conventions in `AGENTS.md` (angles via
`geometry.py`, seeded determinism, serialisable models, docs-in-sync).

---

## Problem

shiftsim today is a single-handed tactics sandbox on a windward-leeward course
with **no boat-on-boat interaction** (`AGENTS.md` → "Doesn't"). The start — and
the lanes just after it — is exactly where boats *do* interact: a boat to
windward and ahead casts **dirty air** ("bad air") on the boats to leeward and
astern, and the highest-leverage question is *what should the gassed boat have
done instead?*

We want to set up a **start-line situation** — place named boats relative to the
line, give them physical/performance parameters, model and **visualise** the bad
air each boat casts, run it, and then **re-run alternative reactions** to compare
outcomes (the existing compare machinery).

## Scope (this PR)

- **Start-line geometry** — a `StartLine` (committee-boat end + pin end) on the
  `Course`, square to the wind by default, and helpers to place a boat at a
  fraction along the line with an offset to leeward ("rows back").
- **Named boats** — already supported (`BoatConfig.name`); surfaced on the line.
- **Boat parameters** — add `length` (LOA) and `beam` to `BoatConfig`. Speed is
  the polar (existing `max_speed`); the start heading follows the boat's
  `initial_tack` + the wind (the boat sails its polar angle, as today).
- **Bad-air model** — a new deterministic `badair.py`: each boat casts a
  wind-shadow cone downwind; a boat inside it sees reduced true wind speed and so
  sails slower. Integrated into the step loop without breaking determinism.
- **Visualisation** — draw the start line and each boat's translucent shadow cone
  in the web replay; tint a boat by how gassed it is; scale the glyph by length.
- **Run / compare** — reuse metrics + replay; "simulate an alternative reaction"
  = change a boat's placement/strategy/tack and re-run.

## Out of scope (follow-ups, already deferred on #13)

- Generalising the situation to **any course position** (not just the start).
- **helmlog import** — seeding a situation from a timestamped helmlog moment. The
  situation JSON below is kept serialisable so an exporter can target it later.
- Right-of-way / rules, contact, lee-bow *direction* bending (v1 models the speed
  loss only — see "Decisions").

## Design

### 1. Start-line geometry (`course.py`)

```python
@dataclass
class StartLine:
    committee: Vec   # starboard end (right, looking upwind)
    pin: Vec         # port end (left, looking upwind)
```

- `Course` gains `start_line: StartLine | None = None`, round-tripped in
  `to_dict`/`from_dict`.
- `start_line_across(twd, length, center=(0,0))` builds a line of `length` metres
  **perpendicular to the wind axis** (square to the first beat), centred at
  `center`; committee on the right looking upwind, pin on the left. Right
  (looking upwind, i.e. toward `unit(twd)`) is `unit(twd+90)`.
- `Course.place_on_line(fraction, behind=0.0)` returns a position `fraction` of
  the way from **pin (0.0) → committee (1.0)**, moved `behind` metres to leeward
  (down the `−unit(twd)` axis). Requires a `start_line`.
- `windward_leeward(..., line_length=0.0)` attaches a start line across the start
  when `line_length > 0`.

### 2. Boat parameters (`boat.py`)

`BoatConfig` gains `length: float = 6.0` and `beam: float = 2.0` (metres). These
feed the shadow size and the viz footprint; defaults match a typical dinghy/keel
sportboat and leave every existing scenario unchanged.

### 3. Bad-air model (`badair.py`)

A boat disturbs the air **to leeward and astern** — a wedge blown downwind. We
model it as a cone whose centreline is the **true-wind downwind direction**
(`twd + 180`) from the casting boat — true wind, not apparent, to stay
seed-independent and deterministic. The downwind-of-an-upwind-boat direction *is*
aft-and-to-leeward, so this captures "to leeward and astern".

`shadow_loss(caster_pos, caster_len, victim_pos, twd, p) -> float` in `[0, 1]`:

1. `rel = victim_pos − caster_pos`; downwind axis `d = unit(twd+180)`.
2. `along = dot(rel, d)`. If `along ≤ 0` → **0** (no shadow upwind/abeam-upwind).
3. `reach = p.length × caster_len` (boat-lengths of reach). If `along > reach` → 0.
4. `cross = |rel − along·d|`. Cone half-width `w = beam_base + along·tan(p.half_angle)`.
   If `cross > w` → 0.
5. Linear falloffs `f_along = 1 − along/reach`, `f_cross = 1 − cross/w`.
6. `loss = p.max_loss × f_along × f_cross`, clamped to `[0, p.max_loss]`.

Multiple casters combine by independent attenuation:
`total = 1 − Π(1 − loss_i)`, then **capped at `p.cap`** (default 0.85) so a boat
is never fully becalmed — a movement safety net analogous to the layline EMA;
it keeps any situation finishing. The victim's effective wind is
`tws_eff = tws × (1 − total)`, fed to the polar, so it sails slower.

**Parameters** live on `RunConfig` (global knobs, like the other safety-net
tunables), all serialisable:

| knob | default | meaning |
|---|---|---|
| `badair_enabled` | `False` | master switch (off ⇒ engine identical to today) |
| `badair_length` | `8.0` | shadow reach in **boat lengths** |
| `badair_half_angle` | `12.0` | cone half-angle (deg) |
| `badair_max_loss` | `0.40` | max fractional TWS loss at the transom |
| `badair_cap` | `0.85` | max combined loss (never fully becalmed) |

### 4. Simulator integration — order-independent (`simulator.py`)

Bad air makes a boat's local wind depend on the *other* boats, so the per-boat
loop is no longer independent. To keep the run **deterministic and
order-independent**, each step is two-phase:

1. **Snapshot phase** — before any boat moves this step, compute every boat's
   wind multiplier from all *other* boats' **current** positions/lengths
   (`badair.shadow_multipliers`). Because every multiplier reads only
   start-of-step positions, the result does not depend on boat order.
2. **Step phase** — `step_boat(b, t, record, wind_mult)` multiplies the boat's
   local `tws` by its precomputed `wind_mult`. Everything downstream (polar
   speed, laylines, strategy) is unchanged.

The suffered multiplier is recorded on each `Sample` (`wind_mult`, default `1.0`)
for the viewer and metrics. With `badair_enabled = False` the multipliers are all
`1.0` and the run is byte-for-byte identical to today (guarded by a test).

This is a **safety-net-style** addition: bad air slows a boat honestly but the
`cap` prevents a pathological becalming, and we do **not** weaken laylines or the
thrash-breaker to accommodate it.

### 5. Metrics (`metrics.py`)

`BoatResult` gains `pct_time_in_badair` — the fraction of upwind samples sailed
meaningfully gassed (`wind_mult < 0.98`). It's the "why" for a start-line loss
("you spent 40% of the first beat in his dirt") and rides along in the replay
results payload.

### 6. Replay + viewer (`report.py`, `web/index.html`, `web/docs.html`)

- `replay_data` exports: `course.start_line`, each boat's `length`/`beam`, a
  per-frame `mult`, and a top-level `badair` block (`enabled`, `length`,
  `half_angle`, `max_loss`) so the viewer draws cones with the **same** geometry
  the engine used (the model stays authoritative in Python; the viewer only draws
  the shape and tints the boat by the engine-computed `mult`).
- Viewer: draw the start line (committee square + pin buoy + line), each boat's
  translucent shadow cone downwind when `badair.enabled`, tint a boat toward red
  as `mult` drops, and scale the boat glyph by `length`/`beam`.
- Controls: a **Start line** section (line length, "model bad air" + reach/angle/
  loss) and per-boat **line pos** / **rows back** / **length** / **beam** inputs.
- Every new field gets a `data-help` key, a `HELP` entry, and a matching
  anchored section in `web/docs.html` (CI-enforced docs-in-sync).

### 7. Situation JSON (serialisable; helmlog-import-ready)

A start-line situation is just a scenario with a start line, per-boat placement,
and bad air enabled — e.g. `scenarios/start_line_badair.json`:

```json
{
  "course": {"type": "windward_leeward", "beat_length": 900, "line_length": 120},
  "run": {"badair_enabled": true},
  "boats": [
    {"name": "Leeward", "start": {"line_pos": 0.35, "behind": 0}, "length": 6.5,
     "beam": 2.4, "initial_tack": "starboard", "strategy": {"name": "minimize_tacks"}}
  ]
}
```

`boat.start = {line_pos, behind}` places the boat via `Course.place_on_line`;
absent a start line (or placement) the boat starts at `course.start` as today. A
future helmlog exporter writes this same shape.

## Decisions / trade-offs

- **Speed loss only (no direction bend) in v1.** Real bad air also *bends* the
  wind (the lee-bow effect). v1 models the **velocity** deficit only — it's the
  dominant, easiest-to-defend effect and keeps determinism simple. "Tack for
  clear air" still emerges as a *tactical* choice you study by re-running with a
  different tack/strategy, which is exactly the "alternative reaction" use case.
  Direction bending is a documented follow-up.
- **True-wind shadow axis,** not apparent wind: deterministic and seed-free, and
  within a few degrees of apparent for these speeds.
- **Default off.** Existing scenarios (and the tactical regression tests, where
  all boats start stacked at the origin) are unchanged; situations opt in and
  place boats at distinct points on the line.
- **`cap` is a safety net,** not a tuning knob to rescue a bad tactic — same
  philosophy as the layline EMA and thrash-breaker.

## Verification / test plan (`tests/test_start_line.py`)

- **Geometry:** `start_line_across` puts committee to the right looking upwind and
  the line square to the wind; `place_on_line` interpolates pin→committee and
  offsets to leeward.
- **Shadow model:** loss > 0 directly downwind within reach; **0** upwind, beyond
  reach, or outside the cone; monotonically decreasing with distance; always in
  `[0, cap]`.
- **Order independence / determinism:** `shadow_multipliers` invariant to boat
  order; a bad-air scenario satisfies `run() == run()`.
- **Back-compat:** `badair_enabled = False` ⇒ all multipliers `1.0` and a 2-boat
  run is identical with the flag absent.
- **Outcome (the headline):** two identical boats, B placed directly in A's bad
  air → B finishes behind A; re-run B onto the opposite tack (sails to clear air)
  → B finishes faster than the gassed-straight B. This is the "alternative
  reaction" the feature exists to study.
- **Serialisation:** a situation JSON with start line + placement + length/beam +
  bad-air config round-trips and runs.
- All four CI checks + the docs-anchor `comm` check pass.
