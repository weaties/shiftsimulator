"""Wind field models.

A :class:`WindField` answers one question: *given a time and a position, what is
the wind?* It returns ``(twd, tws)`` -- true wind direction (degrees, FROM) and
true wind speed (knots).

The interface takes position **now** even though the built-in fields are uniform
in space, so that a spatial field can be dropped in later without touching the
simulator or strategies. Everything is seeded for reproducibility: the same
config + seed always yields the identical wind, so two strategies face exactly
the same conditions (a fair A/B test).

Compose fields with :class:`CompositeWind` to, e.g., put an oscillation on top of
a persistent trend with puffs.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .geometry import Vec, wrap360


class WindField:
    """Base class. Subclasses implement :meth:`at`."""

    def at(self, t: float, pos: Vec) -> tuple[float, float]:
        """Return ``(twd_deg, tws_kn)`` at time ``t`` (s) and ``pos`` (m)."""
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError


@dataclass
class SteadyWind(WindField):
    """Constant wind. The control case."""

    twd: float = 0.0
    tws: float = 10.0

    def at(self, t: float, pos: Vec) -> tuple[float, float]:
        return (wrap360(self.twd), self.tws)

    def to_dict(self) -> dict:
        return {"type": "steady", "twd": self.twd, "tws": self.tws}


@dataclass
class OscillatingWind(WindField):
    """Direction swings sinusoidally about a mean -- the classic shifty day.

    ``amplitude`` is the peak swing each way (deg), ``period`` the full cycle
    time (s). ``phase`` (deg) shifts where in the cycle t=0 sits. This is the
    scenario where "tack on the headers" should beat sailing straight.
    """

    mean_twd: float = 0.0
    amplitude: float = 10.0
    period: float = 240.0
    phase: float = 0.0
    tws: float = 10.0

    def at(self, t: float, pos: Vec) -> tuple[float, float]:
        ph = math.radians(self.phase)
        twd = self.mean_twd + self.amplitude * math.sin(2 * math.pi * t / self.period + ph)
        return (wrap360(twd), self.tws)

    def to_dict(self) -> dict:
        return {
            "type": "oscillating",
            "mean_twd": self.mean_twd,
            "amplitude": self.amplitude,
            "period": self.period,
            "phase": self.phase,
            "tws": self.tws,
        }


@dataclass
class PersistentShift(WindField):
    """Direction trends steadily one way -- a persistent shift.

    The wind goes from ``start_twd`` toward ``start_twd + total_shift`` linearly
    over ``duration`` seconds, then holds. Here the winning move is usually to
    sail toward the new wind first and minimise tacks, not to tack on every
    wobble.
    """

    start_twd: float = 0.0
    total_shift: float = 20.0
    duration: float = 600.0
    tws: float = 10.0

    def at(self, t: float, pos: Vec) -> tuple[float, float]:
        frac = min(1.0, max(0.0, t / self.duration)) if self.duration > 0 else 1.0
        return (wrap360(self.start_twd + self.total_shift * frac), self.tws)

    def to_dict(self) -> dict:
        return {
            "type": "persistent",
            "start_twd": self.start_twd,
            "total_shift": self.total_shift,
            "duration": self.duration,
            "tws": self.tws,
        }


@dataclass
class PuffyWind(WindField):
    """Velocity (and optionally a little direction) varies as smooth noise.

    Models puffs and lulls by summing a few sine waves with seeded random
    periods/phases -- continuous, repeatable, no sharp steps. ``gust_fraction``
    is the peak +/- variation in speed (0.3 = +/-30%); ``veer`` adds a small
    direction wobble that often accompanies pressure changes.
    """

    base_tws: float = 10.0
    base_twd: float = 0.0
    gust_fraction: float = 0.3
    veer: float = 3.0
    n_components: int = 4
    seed: int = 0
    _periods: list[float] = field(default_factory=list, repr=False)
    _phases: list[float] = field(default_factory=list, repr=False)
    _weights: list[float] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        rng = random.Random(self.seed)
        for _ in range(self.n_components):
            self._periods.append(rng.uniform(30.0, 180.0))
            self._phases.append(rng.uniform(0, 2 * math.pi))
            self._weights.append(rng.uniform(0.4, 1.0))
        s = sum(self._weights) or 1.0
        self._weights = [w / s for w in self._weights]

    def _noise(self, t: float, salt: float) -> float:
        v = 0.0
        for p, ph, w in zip(self._periods, self._phases, self._weights, strict=False):
            v += w * math.sin(2 * math.pi * t / p + ph + salt)
        return v  # roughly in [-1, 1]

    def at(self, t: float, pos: Vec) -> tuple[float, float]:
        tws = self.base_tws * (1.0 + self.gust_fraction * self._noise(t, 0.0))
        twd = self.base_twd + self.veer * self._noise(t, 1.7)
        return (wrap360(twd), max(0.1, tws))

    def to_dict(self) -> dict:
        return {
            "type": "puffy",
            "base_tws": self.base_tws,
            "base_twd": self.base_twd,
            "gust_fraction": self.gust_fraction,
            "veer": self.veer,
            "n_components": self.n_components,
            "seed": self.seed,
        }


@dataclass
class CompositeWind(WindField):
    """Sum of several fields. Direction deltas and speed are combined.

    The first field is the *base* (its TWD and TWS are the baseline); every
    subsequent field contributes its **deviation** from its own base direction
    and a multiplicative speed effect. In practice: list a PersistentShift or
    SteadyWind first, then layer OscillatingWind / PuffyWind on top.
    """

    fields: list[WindField] = field(default_factory=list)

    def at(self, t: float, pos: Vec) -> tuple[float, float]:
        if not self.fields:
            return (0.0, 10.0)
        base_twd, base_tws = self.fields[0].at(t, pos)
        twd, tws = base_twd, base_tws
        for f in self.fields[1:]:
            ftwd, ftws = f.at(t, pos)
            # contribute this field's own deviation from its nominal direction
            nominal = _nominal_twd(f, t)
            twd += ((ftwd - nominal + 180) % 360) - 180
            nom_tws = _nominal_tws(f)
            if nom_tws:
                tws *= ftws / nom_tws
        return (wrap360(twd), max(0.1, tws))

    def to_dict(self) -> dict:
        return {"type": "composite", "fields": [f.to_dict() for f in self.fields]}


def _nominal_twd(f: WindField, t: float) -> float:
    if isinstance(f, OscillatingWind):
        return f.mean_twd
    if isinstance(f, PuffyWind):
        return f.base_twd
    if isinstance(f, PersistentShift):
        return f.start_twd
    if isinstance(f, SteadyWind):
        return f.twd
    return f.at(t, (0.0, 0.0))[0]


def _nominal_tws(f: WindField) -> float:
    if isinstance(f, PuffyWind):
        return f.base_tws
    if isinstance(f, (OscillatingWind, PersistentShift)):
        return f.tws
    if isinstance(f, SteadyWind):
        return f.tws
    return 0.0


_REGISTRY = {
    "steady": SteadyWind,
    "oscillating": OscillatingWind,
    "persistent": PersistentShift,
    "puffy": PuffyWind,
}


def wind_from_dict(d: dict) -> WindField:
    """Reconstruct a WindField from its ``to_dict`` form (used by scenario load)."""
    t = d["type"]
    if t == "composite":
        return CompositeWind(fields=[wind_from_dict(x) for x in d["fields"]])
    cls = _REGISTRY[t]
    kwargs = {k: v for k, v in d.items() if k != "type"}
    return cls(**kwargs)
