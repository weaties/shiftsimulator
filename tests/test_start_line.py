"""Start-line situations: line geometry, the bad-air model, and outcomes.

The headline is the *outcome* test (``test_clearing_bad_air_helps``): a boat
stuck in another's dirty air loses, and tacking out to clear air — the
"alternative reaction" the feature exists to study — measurably improves it.
The rest pin the geometry, the determinism guarantee (bad air makes a boat's
wind depend on the others, so the step is order-independent by construction),
and back-compat (flag off ⇒ engine unchanged).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.badair import BadAirParams, shadow_loss, shadow_multipliers
from shiftsim.boat import BoatConfig, BoatState
from shiftsim.course import Course, place_on_line, start_line_across, windward_leeward
from shiftsim.geometry import norm, sub
from shiftsim.polar import synthetic_polar
from shiftsim.scenario import Scenario
from shiftsim.simulator import RunConfig, simulate
from shiftsim.strategy import MinimizeTacks
from shiftsim.wind import SteadyWind

# bad air from the north (wind FROM 0): downwind is due south (−y).
P = BadAirParams(enabled=True, length=8.0, half_angle=12.0, max_loss=0.4, cap=0.85)


# --- start-line geometry --------------------------------------------------


def test_start_line_committee_is_to_windward_right() -> None:
    # wind from north: looking upwind (north) the committee (starboard) end is
    # to the East (+x), the pin (port) to the West (−x); line is square to wind.
    line = start_line_across(twd=0.0, length=100.0)
    assert line.committee[0] > 0 and abs(line.committee[1]) < 1e-9
    assert line.pin[0] < 0 and abs(line.pin[1]) < 1e-9
    assert abs(line.committee[0] - 50.0) < 1e-9


def test_place_on_line_interpolates_and_offsets_to_leeward() -> None:
    line = start_line_across(twd=0.0, length=100.0)
    # pin end at fraction 0, committee at 1, midpoint at 0.5
    assert norm(sub(place_on_line(line, 0.0, 0.0, twd=0.0), line.pin)) < 1e-9
    assert norm(sub(place_on_line(line, 1.0, 0.0, twd=0.0), line.committee)) < 1e-9
    mid = place_on_line(line, 0.5, 0.0, twd=0.0)
    assert abs(mid[0]) < 1e-9 and abs(mid[1]) < 1e-9
    # "behind" moves to leeward (downwind = south, −y)
    back = place_on_line(line, 0.5, 30.0, twd=0.0)
    assert back[1] < -29.0


def test_windward_leeward_attaches_start_line() -> None:
    c = windward_leeward(beat_length=900, mean_twd=0.0, line_length=120.0)
    assert c.start_line is not None
    assert abs(c.start_line.committee[0] - 60.0) < 1e-9
    # round-trips through JSON
    c2 = Course.from_dict(c.to_dict())
    assert c2.start_line is not None
    assert abs(c2.start_line.pin[0] - c.start_line.pin[0]) < 1e-9


# --- the shadow model -----------------------------------------------------


def test_shadow_only_downwind_within_the_cone() -> None:
    caster, clen = (0.0, 0.0), 6.0  # reach = 8 * 6 = 48 m
    # directly downwind (south), close in: gassed
    assert shadow_loss(caster, clen, (0.0, -10.0), twd=0.0, p=P) > 0.0
    # upwind (north): never gassed
    assert shadow_loss(caster, clen, (0.0, 10.0), twd=0.0, p=P) == 0.0
    # beyond reach: clean
    assert shadow_loss(caster, clen, (0.0, -60.0), twd=0.0, p=P) == 0.0
    # far to the side (outside the cone): clean
    assert shadow_loss(caster, clen, (40.0, -10.0), twd=0.0, p=P) == 0.0


def test_shadow_decreases_with_distance_and_is_bounded() -> None:
    caster, clen = (0.0, 0.0), 6.0
    near = shadow_loss(caster, clen, (0.0, -5.0), twd=0.0, p=P)
    far = shadow_loss(caster, clen, (0.0, -40.0), twd=0.0, p=P)
    assert near > far > 0.0
    assert 0.0 <= near <= P.max_loss


def test_multipliers_are_order_independent() -> None:
    # (pos, length, twd_at_pos) for three boats stacked down the wind axis
    boats = [((0.0, 0.0), 6.0, 0.0), ((0.0, -12.0), 6.0, 0.0), ((0.0, -24.0), 6.0, 0.0)]
    m = shadow_multipliers(boats, P)
    m_rev = shadow_multipliers(list(reversed(boats)), P)
    assert m == list(reversed(m_rev))
    # the windward (first) boat is clean; the downwind ones are gassed
    assert m[0] == 1.0 and m[1] < 1.0 and m[2] < 1.0


def test_disabled_means_no_loss() -> None:
    off = BadAirParams(enabled=False)
    boats = [((0.0, 0.0), 6.0, 0.0), ((0.0, -10.0), 6.0, 0.0)]
    assert shadow_multipliers(boats, off) == [1.0, 1.0]


def test_badair_off_run_is_unchanged() -> None:
    # two boats started apart; a run with bad air explicitly off must match the
    # default (flag absent) run exactly — proves the feature is inert when off.
    def run(rc: RunConfig) -> list:
        boats = [
            BoatState(_cfg("A"), pos=(-30.0, 0.0), tack="starboard"),
            BoatState(_cfg("B"), pos=(30.0, 0.0), tack="starboard"),
        ]
        simulate(boats, SteadyWind(twd=0, tws=10), windward_leeward(800, 0.0), 0.0, rc)
        return [(b.finish_time, b.n_tacks) for b in boats]

    assert run(RunConfig(max_time=2000)) == run(RunConfig(max_time=2000, badair_enabled=False))


# --- determinism + outcomes ------------------------------------------------


def _cfg(name: str, length: float = 6.0) -> BoatConfig:
    return BoatConfig(name=name, polar=synthetic_polar(), strategy=MinimizeTacks(), length=length)


def _situation(b_tack: str) -> dict:
    # A clean on the line; B 30 m dead downwind of A, in A's dirty air.
    return {
        "name": "start-line",
        "ref_twd": 0,
        "wind": {"type": "steady", "twd": 0, "tws": 10},
        "course": {"type": "windward_leeward", "beat_length": 900, "line_length": 120},
        "run": {"max_time": 2400, "badair_enabled": True},
        "boats": [
            {
                "name": "A",
                "start": {"line_pos": 0.5, "behind": 0},
                "initial_tack": "starboard",
                "strategy": {"name": "minimize_tacks"},
            },
            {
                "name": "B",
                "start": {"line_pos": 0.5, "behind": 30},
                "initial_tack": b_tack,
                "strategy": {"name": "minimize_tacks"},
            },
        ],
    }


def test_badair_scenario_is_deterministic() -> None:
    def run() -> list:
        sc = Scenario.from_dict(_situation("starboard"))
        return [(b.finish_time, b.n_tacks, b.n_gybes) for b in sc.run_sim()]

    assert run() == run()


def test_clearing_bad_air_helps() -> None:
    # B sitting in A's dirt (same tack) loses to A...
    sc = Scenario.from_dict(_situation("starboard"))
    res = {b.cfg.name: b for b in sc.run_sim()}
    a, b_gassed = res["A"], res["B"]
    assert a.finished and b_gassed.finished
    assert a.finish_time < b_gassed.finish_time, "clean A should beat the gassed B"
    assert b_gassed.history and any(s.wind_mult < 0.98 for s in b_gassed.history)

    # ...and B's alternative reaction — tack off to clear air — is faster than
    # sitting in the bad air on the same tack.
    sc2 = Scenario.from_dict(_situation("port"))
    b_clear = next(x for x in sc2.run_sim() if x.cfg.name == "B")
    assert b_clear.finished
    assert b_clear.finish_time < b_gassed.finish_time, "clearing the air should help B"


def test_explicit_start_line_overrides_square_one() -> None:
    # a dragged / biased line: endpoints given explicitly, not square to the wind
    cfg = _situation("starboard")
    cfg["course"]["start_line"] = {"committee": [70, 10], "pin": [-50, -10]}
    sc = Scenario.from_dict(cfg)
    assert sc.course.start_line is not None
    assert sc.course.start_line.committee == (70, 10)
    assert sc.course.start_line.pin == (-50, -10)


def test_boat_absolute_start_pos() -> None:
    # a dragged boat: absolute position overrides line placement
    cfg = _situation("starboard")
    cfg["boats"][0]["start"] = {"pos": [12.5, -7.0]}
    sc = Scenario.from_dict(cfg)
    assert sc.starts[0] == (12.5, -7.0)
    assert all(s.finished for s in sc.run_sim())


def test_dragged_boats_keep_distinct_positions() -> None:
    # regression for #17: several boats each given a distinct dragged start.pos
    # must each start where they were placed, not collapse to one point.
    cfg = {
        "name": "drag",
        "ref_twd": 0,
        "wind": {"type": "oscillating", "mean_twd": 0, "amplitude": 12, "period": 200, "tws": 10},
        "course": {
            "type": "windward_leeward",
            "beat_length": 1200,
            "line_length": 101,
            "start_line": {"committee": [50.8, -5.7], "pin": [-49.4, 8.1]},
        },
        "run": {"max_time": 3000},
        "boats": [
            {"name": "A", "start": {"pos": [-23.1, -13.1]}, "strategy": {"name": "minimize_tacks"}},
            {"name": "B", "start": {"pos": [5.6, -0.9]}, "strategy": {"name": "minimize_tacks"}},
            {"name": "C", "start": {"pos": [29.8, -1.2]}, "strategy": {"name": "minimize_tacks"}},
        ],
    }
    sc = Scenario.from_dict(cfg)
    assert sc.starts == [(-23.1, -13.1), (5.6, -0.9), (29.8, -1.2)]
    states = sc.run_sim()
    firsts = [s.history[0].pos for s in states]
    assert len(set(firsts)) == 3, f"boats collapsed to {firsts}"


def test_situation_round_trips_with_length_and_beam() -> None:
    cfg = _situation("starboard")
    cfg["boats"][0]["length"] = 6.5
    cfg["boats"][0]["beam"] = 2.4
    sc = Scenario.from_dict(cfg)
    assert sc.boats[0].length == 6.5 and sc.boats[0].beam == 2.4
    states = sc.run_sim()
    assert all(s.finished for s in states)
