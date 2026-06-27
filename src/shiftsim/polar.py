"""Boat polars: boat speed as a function of true wind angle (TWA) and speed (TWS).

A :class:`Polar` is the heart of the boat model. From it we derive the optimal
upwind and downwind sailing angles (the angles that maximise velocity-made-good
toward / away from the wind), which is what makes "sailing the shifts" produce
realistic gains and losses.

Two ways to get a polar:

* :func:`synthetic_polar` -- generate a plausible curve from a few parameters,
  so you can start with no data at all.
* :meth:`Polar.from_csv` -- import a real polar table (rows = TWA, columns = TWS),
  the de-facto format exported by most VPPs / ORC certificates.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def _interp(x: float, xs: Sequence[float], ys: Sequence[float]) -> float:
    """Linear interpolation with flat extrapolation. ``xs`` must be ascending."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


@dataclass
class Polar:
    """Boat speed lookup over (TWA, TWS).

    ``twa`` is ascending degrees (0..180), ``tws`` ascending knots, and
    ``table[i][j]`` is boat speed in knots at ``twa[i]``, ``tws[j]``.
    """

    twa: list[float]
    tws: list[float]
    table: list[list[float]]
    name: str = "polar"

    def __post_init__(self) -> None:
        # memoise the optimal-angle scans; they're called every sim step per boat
        # and the table is immutable, so cache by rounded wind speed.
        self._up_cache: dict[float, tuple[float, float]] = {}
        self._dn_cache: dict[float, tuple[float, float]] = {}

    def speed(self, twa_deg: float, tws_kn: float) -> float:
        """Boat speed (knots) at the given true wind angle and speed.

        Bilinear interpolation; TWA is folded into 0..180 (port/starboard
        symmetric)."""
        a = abs(((twa_deg + 180.0) % 360.0) - 180.0)
        # interpolate along TWS for each bracketing TWA row, then along TWA.
        col = [_interp(tws_kn, self.tws, row) for row in self.table]
        return max(0.0, _interp(a, self.twa, col))

    def best_upwind(self, tws_kn: float) -> tuple[float, float]:
        """Return ``(twa, vmg)`` maximising upwind VMG = speed * cos(twa)."""
        key = round(tws_kn, 1)
        hit = self._up_cache.get(key)
        if hit is not None:
            return hit
        best = (45.0, 0.0)
        a = 20.0
        while a <= 90.0:
            vmg = self.speed(a, tws_kn) * math.cos(math.radians(a))
            if vmg > best[1]:
                best = (a, vmg)
            a += 0.5
        self._up_cache[key] = best
        return best

    def best_downwind(self, tws_kn: float) -> tuple[float, float]:
        """Return ``(twa, vmg)`` maximising downwind VMG = speed * -cos(twa)."""
        key = round(tws_kn, 1)
        hit = self._dn_cache.get(key)
        if hit is not None:
            return hit
        best = (180.0, 0.0)
        a = 90.0
        while a <= 180.0:
            vmg = self.speed(a, tws_kn) * -math.cos(math.radians(a))
            if vmg > best[1]:
                best = (a, vmg)
            a += 0.5
        self._dn_cache[key] = best
        return best

    def to_dict(self) -> dict:
        return {"name": self.name, "twa": self.twa, "tws": self.tws, "table": self.table}

    @classmethod
    def from_dict(cls, d: dict) -> Polar:
        return cls(
            twa=list(d["twa"]),
            tws=list(d["tws"]),
            table=[list(r) for r in d["table"]],
            name=d.get("name", "polar"),
        )

    @classmethod
    def from_csv(cls, path: str, name: str = "") -> Polar:
        """Load a polar from CSV.

        Layout (the common VPP/ORC export form)::

            twa\\tws, 6,  8,  10, 12, ...
            0,        0,  0,  0,  0
            40,       4.9,5.6,6.0,6.2
            52,       5.4,6.1,6.6,6.9
            ...

        The top-left cell is ignored; the first row is TWS values, the first
        column is TWA values, and the body is boat speed in knots. Delimiter is
        auto-detected between comma, semicolon and tab.
        """
        with open(path, newline="") as f:
            sample = f.read(2048)
            f.seek(0)
            delim = ";" if sample.count(";") > sample.count(",") else ","
            if sample.count("\t") > max(sample.count(","), sample.count(";")):
                delim = "\t"
            rows = [r for r in csv.reader(f, delimiter=delim) if any(c.strip() for c in r)]
        header = rows[0]
        tws = [float(c) for c in header[1:] if c.strip()]
        twa: list[float] = []
        table: list[list[float]] = []
        for r in rows[1:]:
            twa.append(float(r[0]))
            table.append([float(c) if c.strip() else 0.0 for c in r[1 : 1 + len(tws)]])
        # reorder ascending TWA just in case
        order = sorted(range(len(twa)), key=lambda i: twa[i])
        twa = [twa[i] for i in order]
        table = [table[i] for i in order]
        return cls(twa=twa, tws=tws, table=table, name=name or path)


# --- synthetic polar generation -------------------------------------------

# Relative speed shape vs TWA (1.0 == fastest point of sail, ~a beam reach).
_SHAPE_TWA = [0, 30, 40, 45, 52, 60, 75, 90, 110, 120, 135, 150, 165, 180]
_SHAPE_REL = [0, 0.45, 0.68, 0.76, 0.88, 0.95, 1.0, 1.02, 1.0, 0.97, 0.90, 0.78, 0.62, 0.52]


def synthetic_polar(
    name: str = "synthetic",
    max_speed: float = 8.0,
    light_air_factor: float = 8.0,
    pointing: float = 1.0,
    tws_grid: Sequence[float] = (4, 6, 8, 10, 12, 16, 20, 25),
) -> Polar:
    """Build a plausible polar from a few intuitive parameters.

    Parameters
    ----------
    max_speed:
        Roughly the boat's top speed in strong breeze (knots). Bigger / faster
        boats use a higher value.
    light_air_factor:
        How quickly the boat gets up to speed as wind builds. Boat speed scales
        as ``max_speed * (1 - exp(-tws / light_air_factor))``; smaller = the boat
        powers up sooner in light air.
    pointing:
        >1 sharpens the upwind shoulder (the boat points higher, like a keelboat
        with good sails); <1 makes it a fatter, more reaching-oriented curve.
        Useful for giving boats genuinely different optimal tacking angles.
    """
    twa = [float(a) for a in range(0, 181, 5)]
    shape = [_interp(a, _SHAPE_TWA, _SHAPE_REL) for a in twa]
    if pointing != 1.0:
        shape = [_pointing_adjust(a, s, pointing) for a, s in zip(twa, shape, strict=False)]
    tws = list(tws_grid)
    table = []
    for _a, s in zip(twa, shape, strict=False):
        row = [round(max_speed * s * (1.0 - math.exp(-w / light_air_factor)), 3) for w in tws]
        table.append(row)
    return Polar(twa=twa, tws=tws, table=table, name=name)


def _pointing_adjust(twa: float, rel: float, pointing: float) -> float:
    """Boost/cut speed in the upwind range to model better/worse pointing."""
    if 30 <= twa <= 60:
        # boost the 35-50 region for high-pointing boats
        peak = 1.0 - abs(twa - 45) / 15.0
        return rel * (1.0 + 0.12 * (pointing - 1.0) * max(0.0, peak))
    return rel
