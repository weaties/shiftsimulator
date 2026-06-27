"""Maneuver-log recording and the replay/API payload shape.

The web viewer's calculation panel and the /api/simulate endpoint both depend on
these, so they're worth guarding.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.report import replay_data
from shiftsim.scenario import Scenario

CONFIG = {
    "name": "api-test",
    "ref_twd": 0,
    "wind": {"type": "oscillating", "mean_twd": 0, "amplitude": 12, "period": 200, "tws": 10},
    "course": {"type": "windward_leeward", "beat_length": 900, "laps": 1},
    "run": {"dt": 0.5, "max_time": 2400, "sample_every": 4},
    "boats": [
        {
            "name": "HH",
            "color": "#f00",
            "initial_tack": "starboard",
            "maneuver_time": 12,
            "maneuver_speed_factor": 0.45,
            "strategy": {"name": "tack_at_half_header", "amplitude": 12, "fraction": 0.5},
            "polar": {"type": "synthetic", "max_speed": 7.5},
        },
    ],
}


def _run() -> tuple[Scenario, dict]:
    sc = Scenario.from_dict(CONFIG)  # exactly what /api/simulate does
    return sc, replay_data(sc, sc.run_sim())


def test_api_payload_shape() -> None:
    sc, d = _run()
    assert {"name", "bounds", "course", "boats", "results", "ladder_gain"} <= set(d)
    b = d["boats"][0]
    assert "frames" in b and "maneuvers" in b
    assert b["frames"][0].keys() >= {"t", "x", "y", "hdg", "twd", "lad"}


def test_maneuvers_have_calculations() -> None:
    sc, d = _run()
    mans = d["boats"][0]["maneuvers"]
    assert mans, "expected at least one maneuver"
    for m in mans:
        assert m["kind"] in ("tack", "gybe")
        assert m["reason"] in (
            "strategy",
            "layline",
            "layline_approach",
            "layline_recovery",
            "sailing_away",
        )
        assert "explain" in m and "rule" in m["explain"]
        assert m["approx_distance_lost_m"] >= 0


def test_strategy_explain_matches_decision() -> None:
    # a half-header strategy maneuver should carry the headed/trigger numbers,
    # and a strategy-reason tack means headed >= trigger.
    sc, d = _run()
    strat = [m for m in d["boats"][0]["maneuvers"] if m["reason"] == "strategy"]
    assert strat, "expected strategy-driven tacks"
    e = strat[0]["explain"]
    assert {"headed_deg", "trigger_deg", "amplitude_deg"} <= set(e)
    assert e["headed_deg"] >= e["trigger_deg"] - 0.6  # within one timestep
