"""Wind-field behaviour and reproducibility."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.wind import (
    CompositeWind,
    OscillatingWind,
    PersistentShift,
    PuffyWind,
    SteadyWind,
    wind_from_dict,
)


def test_oscillating_stays_within_amplitude() -> None:
    w = OscillatingWind(mean_twd=0, amplitude=12, period=200, tws=10)
    dirs = [w.at(t, (0, 0))[0] for t in range(0, 200, 5)]
    signed = [d - 360 if d > 180 else d for d in dirs]
    assert max(signed) <= 12.001 and min(signed) >= -12.001


def test_persistent_endpoints() -> None:
    w = PersistentShift(start_twd=0, total_shift=20, duration=500, tws=10)
    assert abs(w.at(0, (0, 0))[0] - 0) < 1e-6
    assert abs(w.at(1000, (0, 0))[0] - 20) < 1e-6  # holds after duration


def test_puffy_is_deterministic_by_seed() -> None:
    a = PuffyWind(seed=7)
    b = PuffyWind(seed=7)
    c = PuffyWind(seed=8)
    assert a.at(33, (0, 0)) == b.at(33, (0, 0))
    assert a.at(33, (0, 0)) != c.at(33, (0, 0))


def test_composite_layers_oscillation_on_trend() -> None:
    w = CompositeWind(
        fields=[
            PersistentShift(start_twd=0, total_shift=20, duration=500, tws=10),
            OscillatingWind(mean_twd=0, amplitude=8, period=120),
        ]
    )
    # near t=0 oscillation ~0; direction tracks the persistent base
    d0 = w.at(0, (0, 0))[0]
    assert abs((d0 + 180) % 360 - 180) < 8.1


def test_roundtrip_dict() -> None:
    for w in (
        SteadyWind(twd=5, tws=9),
        OscillatingWind(amplitude=10),
        PersistentShift(total_shift=15),
        PuffyWind(seed=3),
    ):
        w2 = wind_from_dict(w.to_dict())
        assert w2.at(50, (0, 0)) == w.at(50, (0, 0))
