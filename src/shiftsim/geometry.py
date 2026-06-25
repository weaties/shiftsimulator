"""2D geometry and angle helpers.

Coordinate convention
---------------------
- Positions are ``(x, y)`` tuples in metres, ``x`` = East, ``y`` = North.
- Bearings are in **degrees**, ``0`` = North, ``90`` = East, increasing
  clockwise (nautical convention).
- Wind direction (TWD) is the direction the wind blows **FROM**, also in
  bearing degrees (so a Northerly = TWD 0). The windward mark therefore lies
  in the ``unit(TWD)`` direction from anywhere on the course.

Keeping every angle in one convention is the single most important thing for
this project staying debuggable, so all conversions live here.
"""
from __future__ import annotations

import math
from typing import Tuple

Vec = Tuple[float, float]


def unit(bearing_deg: float) -> Vec:
    """Unit vector pointing along ``bearing_deg`` (0=N, 90=E)."""
    r = math.radians(bearing_deg)
    return (math.sin(r), math.cos(r))


def bearing_of(v: Vec) -> float:
    """Bearing (0..360) of vector ``v`` = (east, north)."""
    return wrap360(math.degrees(math.atan2(v[0], v[1])))


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1])


def scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Vec, b: Vec) -> float:
    """z-component of a x b. Sign tells you which side of ``a`` that ``b`` is on."""
    return a[0] * b[1] - a[1] * b[0]


def norm(a: Vec) -> float:
    return math.hypot(a[0], a[1])


def wrap360(deg: float) -> float:
    """Wrap an angle to [0, 360)."""
    return deg % 360.0


def wrap180(deg: float) -> float:
    """Wrap an angle to (-180, 180]."""
    d = (deg + 180.0) % 360.0 - 180.0
    return d + 360.0 if d <= -180.0 else d


def angle_between(a_deg: float, b_deg: float) -> float:
    """Smallest absolute difference between two bearings, in [0, 180]."""
    return abs(wrap180(a_deg - b_deg))
