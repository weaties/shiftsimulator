"""End-to-end simulation behaviour and the headline tactical results.

These are the regression tests that guard realism: if a change makes tacking on
the headers stop beating sailing straight, something is wrong with the model.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.boat import BoatConfig, BoatState
from shiftsim.course import windward_leeward
from shiftsim.polar import synthetic_polar
from shiftsim.scenario import Scenario
from shiftsim.simulator import RunConfig, heading_for, simulate
from shiftsim.strategy import MinimizeTacks
from shiftsim.wind import SteadyWind


def _boat(name, strat, tack="starboard"):
    return BoatConfig(name=name, polar=synthetic_polar(), strategy=strat,
                      initial_tack=tack)


def test_heading_convention():
    # wind from north (0); starboard tack beats up the left, port up the right
    assert abs(heading_for("starboard", 0, 42) - 318) < 1e-6
    assert abs(heading_for("port", 0, 42) - 42) < 1e-6


def test_boat_finishes_steady_wind():
    b = BoatState(cfg=_boat("m", MinimizeTacks()), pos=(0, 0), tack="starboard")
    simulate([b], SteadyWind(twd=0, tws=10), windward_leeward(800, 0.0), 0.0,
             RunConfig(max_time=2000))
    assert b.finished and b.finish_time is not None


def test_determinism():
    def run():
        sc = Scenario.load(os.path.join(os.path.dirname(__file__), "..",
                                        "scenarios", "oscillating_demo.json"))
        return [(b.finish_time, b.n_tacks, b.n_gybes) for b in sc.run_sim()]
    assert run() == run()


def test_tack_on_header_beats_minimize_in_oscillation():
    sc = Scenario.load(os.path.join(os.path.dirname(__file__), "..",
                                    "scenarios", "oscillating_demo.json"))
    res = {b.cfg.name: b for b in sc.run_sim()}
    headers = next(b for n, b in res.items() if "header" in n.lower())
    onetack = next(b for n, b in res.items() if "minimize" in n.lower())
    assert headers.finished and onetack.finished
    assert headers.finish_time < onetack.finish_time


def test_favoured_side_wins_persistent():
    sc = Scenario.load(os.path.join(os.path.dirname(__file__), "..",
                                    "scenarios", "persistent_demo.json"))
    res = {b.cfg.name: b for b in sc.run_sim()}
    right = next(b for n, b in res.items() if "Right side" in n)
    wrong = next(b for n, b in res.items() if "Wrong side" in n)
    assert right.finished and wrong.finished
    assert right.finish_time < wrong.finish_time


def test_header_strategies_quiet_in_steady_wind():
    # Regression for the "boats keep tacking in steady wind" bug: a header is a
    # wind shift, so in STEADY wind a header/half-header strategy must not tack
    # voluntarily -- it should behave like minimize_tacks (layline tacks only),
    # not zig-zag up the course.
    from shiftsim.strategy import TackAtHalfHeader, TackOnHeader
    course = windward_leeward(1200, 0.0)
    base = BoatState(cfg=_boat("base", MinimizeTacks()), pos=(0, 0), tack="starboard")
    simulate([base], SteadyWind(twd=0, tws=10), course, 0.0, RunConfig(max_time=3000))
    for strat in (TackOnHeader(threshold=8), TackAtHalfHeader(amplitude=12, fraction=0.5)):
        b = BoatState(cfg=_boat(strat.name, strat), pos=(0, 0), tack="starboard")
        simulate([b], SteadyWind(twd=0, tws=10), course, 0.0, RunConfig(max_time=3000))
        assert b.finished, strat.name
        assert b.n_tacks <= base.n_tacks, f"{strat.name} tacked in steady wind"


def test_half_header_finishes_and_beats_lift_in_oscillation():
    from shiftsim.strategy import TackAtHalfHeader, TackOnLift
    half = BoatState(cfg=_boat("half", TackAtHalfHeader(amplitude=12, fraction=0.5)),
                     pos=(0, 0), tack="starboard")
    lift = BoatState(cfg=_boat("lift", TackOnLift(threshold=8)), pos=(0, 0), tack="starboard")
    from shiftsim.wind import OscillatingWind
    wind = OscillatingWind(mean_twd=0, amplitude=12, period=200, tws=10)
    course = windward_leeward(1200, 0.0)
    for b in (half, lift):
        simulate([b], wind, course, 0.0, RunConfig(max_time=2400))
    assert half.finished
    assert (half.finish_time or 9e9) < (lift.finish_time or 9e9)


def test_all_boats_finish_demos():
    for f in ("oscillating_demo.json", "persistent_demo.json"):
        sc = Scenario.load(os.path.join(os.path.dirname(__file__), "..", "scenarios", f))
        for b in sc.run_sim():
            assert b.finished, f"{b.cfg.name} did not finish {f}"
