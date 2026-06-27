"""Geometry/angle conventions -- the foundation everything else trusts."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.geometry import angle_between, bearing_of, cross, dot, unit, wrap180, wrap360


def test_unit_compass_directions() -> None:
    n = unit(0)
    e = unit(90)
    s = unit(180)
    w = unit(270)
    assert abs(n[0]) < 1e-9 and abs(n[1] - 1) < 1e-9  # north = +y
    assert abs(e[0] - 1) < 1e-9 and abs(e[1]) < 1e-9  # east  = +x
    assert abs(s[1] + 1) < 1e-9  # south = -y
    assert abs(w[0] + 1) < 1e-9  # west  = -x


def test_bearing_roundtrip() -> None:
    for b in (0, 17, 90, 123, 270, 359):
        assert abs(wrap180(bearing_of(unit(b)) - b)) < 1e-6


def test_wrap_ranges() -> None:
    assert wrap360(370) == 10
    assert wrap360(-10) == 350
    assert wrap180(190) == -170
    assert wrap180(-190) == 170
    assert angle_between(350, 10) == 20


def test_cross_dot_signs() -> None:
    # east x north = +z (right-hand), so cross(E, N) > 0
    assert cross(unit(90), unit(0)) > 0
    assert dot(unit(0), unit(0)) > 0
    assert abs(dot(unit(0), unit(90))) < 1e-9
