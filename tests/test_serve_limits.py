"""Compute caps for the public /api/simulate endpoint.

The simulator is data-only, but it runs on a Raspberry Pi, so the API must
reject configs that would cost too much to run. These guard that boundary.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.serve import LIMITS, RequestTooLarge, validate_request

OK = {
    "ref_twd": 0,
    "wind": {"type": "oscillating", "mean_twd": 0, "amplitude": 12, "period": 200, "tws": 10},
    "course": {"type": "windward_leeward", "beat_length": 1200, "laps": 1},
    "run": {"dt": 0.5, "max_time": 3000, "sample_every": 4},
    "boats": [
        {"name": "A", "strategy": {"name": "minimize_tacks"}, "polar": {"type": "synthetic"}}
    ],
}


def _rejected(cfg: dict) -> bool:
    try:
        validate_request(cfg)
        return False
    except RequestTooLarge:
        return True


def test_valid_config_passes() -> None:
    validate_request(copy.deepcopy(OK))  # should not raise


def test_rejects_no_boats() -> None:
    cfg = copy.deepcopy(OK)
    cfg["boats"] = []
    assert _rejected(cfg)


def test_rejects_too_many_boats() -> None:
    cfg = copy.deepcopy(OK)
    cfg["boats"] = [OK["boats"][0]] * (LIMITS["max_boats"] + 1)
    assert _rejected(cfg)


def test_rejects_tiny_dt() -> None:
    cfg = copy.deepcopy(OK)
    cfg["run"]["dt"] = 0.01
    assert _rejected(cfg)


def test_rejects_huge_max_time() -> None:
    cfg = copy.deepcopy(OK)
    cfg["run"]["max_time"] = LIMITS["max_time"] + 1
    assert _rejected(cfg)


def test_rejects_too_many_laps() -> None:
    cfg = copy.deepcopy(OK)
    cfg["course"]["laps"] = LIMITS["max_laps"] + 1
    assert _rejected(cfg)


def test_rejects_over_budget_combo() -> None:
    # individually-legal values whose product blows the step-boat budget
    cfg = copy.deepcopy(OK)
    cfg["run"]["dt"] = LIMITS["min_dt"]
    cfg["run"]["max_time"] = LIMITS["max_time"]
    cfg["boats"] = [OK["boats"][0]] * LIMITS["max_boats"]
    assert _rejected(cfg)
