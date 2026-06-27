"""Polar realism checks: optimal angles, monotonicity, CSV round-trip."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.polar import Polar, synthetic_polar


def test_synthetic_speed_nonnegative_and_zero_head_to_wind() -> None:
    p = synthetic_polar()
    assert p.speed(0, 10) == 0.0  # can't sail straight into the wind
    assert p.speed(90, 10) > 0


def test_best_upwind_angle_realistic() -> None:
    p = synthetic_polar()
    twa, vmg = p.best_upwind(10)
    assert 30 <= twa <= 55, twa  # close-hauled, not pinching or reaching
    assert vmg > 0


def test_best_downwind_angle_realistic() -> None:
    p = synthetic_polar()
    twa, vmg = p.best_downwind(10)
    assert 120 <= twa <= 180, twa  # a broad reach / run
    assert vmg > 0


def test_speed_increases_with_wind() -> None:
    p = synthetic_polar()
    assert p.speed(60, 6) < p.speed(60, 16)


def test_pointing_parameter_sharpens_upwind() -> None:
    low = synthetic_polar(pointing=0.8).best_upwind(10)[0]
    high = synthetic_polar(pointing=1.4).best_upwind(10)[0]
    # higher-pointing boat sails a tighter (smaller) optimal upwind angle
    assert high <= low + 0.5


def test_csv_roundtrip() -> None:
    p = synthetic_polar(max_speed=7.0)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.csv")
        header = "twa/tws," + ",".join(str(t) for t in p.tws)
        rows = [header] + [
            f"{a}," + ",".join(f"{v:.3f}" for v in row)
            for a, row in zip(p.twa, p.table, strict=False)
        ]
        with open(path, "w") as f:
            f.write("\n".join(rows) + "\n")
        q = Polar.from_csv(path)
    assert abs(q.speed(52, 10) - p.speed(52, 10)) < 1e-3
