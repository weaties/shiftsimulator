"""Physics sanity: the model has to obey the basic rules of sailing.

These are the "known result" regression checks the ``validate-physics`` skill
leans on. If one of these breaks, the simulator is no longer trustworthy even if
nothing crashes.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.boat import BoatConfig, BoatState
from shiftsim.course import windward_leeward
from shiftsim.geometry import wrap180
from shiftsim.polar import synthetic_polar
from shiftsim.simulator import RunConfig, heading_for, simulate
from shiftsim.strategy import MinimizeTacks
from shiftsim.wind import OscillatingWind, SteadyWind


def test_vmg_optimum_beats_neighbours():
    # the chosen upwind angle must actually maximise upwind VMG locally
    p = synthetic_polar()
    twa, vmg = p.best_upwind(10)
    for d in (-4, 4):
        a = twa + d
        assert p.speed(a, 10) * math.cos(math.radians(a)) <= vmg + 1e-9


def test_boat_sails_the_shift_keeps_twa():
    # close-hauled boat keeps a constant TWA, so heading rotates with the wind
    b = BoatState(cfg=BoatConfig(name="m", polar=synthetic_polar(),
                                 strategy=MinimizeTacks()), pos=(0, 0), tack="starboard")
    simulate([b], OscillatingWind(mean_twd=0, amplitude=12, period=200, tws=10),
             windward_leeward(1500, 0.0), 0.0, RunConfig(max_time=2400))
    # on every upwind sample, |heading - twd| should equal the boat's TWA
    for s in b.history:
        if s.boat_speed > 0 and s.twa < 90 and not s.maneuvering and s.leg == 0:
            assert abs(abs(wrap180(s.heading - s.twd)) - s.twa) < 0.5


def test_more_wind_more_speed_in_sim():
    def avg_speed(tws):
        b = BoatState(cfg=BoatConfig(name="m", polar=synthetic_polar(),
                      strategy=MinimizeTacks()), pos=(0, 0), tack="starboard")
        simulate([b], SteadyWind(twd=0, tws=tws), windward_leeward(800, 0.0), 0.0,
                 RunConfig(max_time=4000))
        sp = [s.boat_speed for s in b.history if s.boat_speed > 0]
        return sum(sp) / len(sp)
    assert avg_speed(6) < avg_speed(14)


def test_extra_tacks_cost_distance():
    # same boat, but one tacks on a fixed clock -- it must sail no less distance
    from shiftsim.strategy import FixedInterval
    base = BoatState(cfg=BoatConfig(name="straight", polar=synthetic_polar(),
                     strategy=MinimizeTacks()), pos=(0, 0), tack="starboard")
    busy = BoatState(cfg=BoatConfig(name="busy", polar=synthetic_polar(),
                     strategy=FixedInterval(period=60)), pos=(0, 0), tack="starboard")
    wind = SteadyWind(twd=0, tws=10)
    course = windward_leeward(1000, 0.0)
    simulate([base], wind, course, 0.0, RunConfig(max_time=3000))
    simulate([busy], wind, course, 0.0, RunConfig(max_time=3000))
    assert busy.n_tacks > base.n_tacks
    # extra maneuvers in steady wind never make you faster
    assert (busy.finish_time or 9e9) >= (base.finish_time or 0)


def test_ref_boat_gain_is_zero():
    from shiftsim.metrics import ladder_gain_series
    b1 = BoatState(cfg=BoatConfig(name="a", polar=synthetic_polar(),
                   strategy=MinimizeTacks()), pos=(0, 0), tack="starboard")
    b2 = BoatState(cfg=BoatConfig(name="b", polar=synthetic_polar(),
                   strategy=MinimizeTacks()), pos=(0, 0), tack="port")
    wind = SteadyWind(twd=0, tws=10)
    course = windward_leeward(800, 0.0)
    for b in (b1, b2):
        simulate([b], wind, course, 0.0, RunConfig(max_time=2000))
    g = ladder_gain_series([b1, b2], reference=0)
    assert all(v == 0 for v in g["series"]["a"] if v is not None)
