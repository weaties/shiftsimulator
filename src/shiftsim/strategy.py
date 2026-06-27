"""Tack / gybe decision strategies.

A strategy answers one question each step: *given the wind and where the mark
is -- should I flip tacks right now?* It returns ``True`` to maneuver
voluntarily. (The simulator separately forces a maneuver at the layline so no
boat overstands, and debounces with ``min_time_between_maneuvers``, so strategies
don't have to worry about either.)

Design note -- measure the header from the WIND, not the mark
-------------------------------------------------------------
A "header" is a wind shift that pushes your heading away from the mark. The
tempting shortcut -- "tack when the other tack points closer to the mark" --
is **wrong**: a boat that has simply sailed off to the side of the rhumb line
*also* finds the other tack points closer, with no shift at all. Using that rule
the boat zig-zags up the course even in dead-steady wind (a real bug we hit).

So the header strategies (:class:`_HeaderSense` and subclasses) track a running
mean wind direction and measure how far the wind has shifted **against the
current tack relative to that mean**. Steady wind => no shift => no header =>
sail straight to the layline. Getting to the side of the course is the layline's
job, not the strategy's.

Add your own by subclassing :class:`Strategy` (or :class:`_HeaderSense` if it's
header-based), implementing ``decide``/``explain``, and registering it in
``_REGISTRY`` (see the ``add-boat-strategy`` skill).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import wrap180


@dataclass
class StrategyContext:
    """Read-only snapshot handed to :meth:`Strategy.decide` each step."""

    t: float
    dt: float
    point_of_sail: str  # "upwind" or "downwind"
    tack: str  # current tack: "port" or "starboard"
    twd: float
    tws: float
    twa: float  # the boat's optimal angle off the wind this leg
    heading_current: float  # heading if we stay on this tack
    heading_other: float  # heading if we flip tacks
    bearing_to_mark: float  # bearing from boat to the current target mark
    dist_to_mark: float

    # signed error (deg) between a heading and the mark bearing; smaller = better
    def err(self, heading: float) -> float:
        return abs(wrap180(heading - self.bearing_to_mark))


class Strategy:
    """Base class. ``decide`` returns True to voluntarily tack/gybe now."""

    name = "base"

    def decide(self, ctx: StrategyContext) -> bool:
        return False

    def explain(self, ctx: StrategyContext) -> dict:
        """Read-only snapshot of the numbers behind the current decision.

        Called *after* :meth:`decide` when a maneuver fires, to record *why* the
        boat tacked/gybed. Must not mutate strategy state."""
        return {"rule": self.name}

    def reset(self) -> None:
        """Clear per-run internal state (called at the start of each run)."""

    def to_dict(self) -> dict:
        return {"name": self.name}


class MinimizeTacks(Strategy):
    """Never tack voluntarily -- sail the long board to the layline.

    With an appropriate ``initial_tack`` this is also the "commit to one side"
    play, which is what you want in a persistent shift: pick the side the wind is
    going to, and only tack once (at the layline backstop)."""

    name = "minimize_tacks"

    def decide(self, ctx: StrategyContext) -> bool:
        return False

    def explain(self, ctx: StrategyContext) -> dict:
        return {"rule": "never tacks voluntarily; only forced at the layline"}


class _HeaderSense(Strategy):
    """Shared machinery for header/lift strategies.

    Tracks a running mean wind direction and reports how *headed* the current
    tack is -- the number of degrees the wind has shifted **against** you,
    relative to the mean (positive = headed, negative = lifted).

    Crucially the header is measured from the wind, not from the bearing to the
    mark. That distinction is the whole point: sailing away from the rhumb line
    also makes the other tack "point closer to the mark", but that is *not* a
    header and must not trigger a tack -- otherwise a boat zig-zags even in
    steady wind. With this measure, steady wind => never a header => sail to the
    layline."""

    def __init__(self, mean_tau: float = 90.0) -> None:
        self.mean_tau = float(mean_tau)
        self._mean: float | None = None

    def reset(self) -> None:
        self._mean = None

    def _headed(self, ctx: StrategyContext, update: bool) -> float:
        """Degrees the wind has shifted against the current tack. ``update``
        advances the mean-wind estimate (decide=True, explain=False)."""
        mean = ctx.twd if self._mean is None else self._mean
        if update:
            if self._mean is None:
                self._mean = ctx.twd
            alpha = 1.0 - math.exp(-ctx.dt / max(1e-6, self.mean_tau))
            self._mean = self._mean + alpha * wrap180(ctx.twd - self._mean)
            mean = self._mean
        shift = wrap180(ctx.twd - mean)  # + = veered right of mean
        headed = (-shift) if ctx.tack == "starboard" else shift
        if ctx.point_of_sail == "downwind":
            headed = -headed  # the sense mirrors on a run
        return headed

    @property
    def mean_wind(self) -> float | None:
        return self._mean


class TackOnHeader(_HeaderSense):
    """Stay on the lifted tack: tack/gybe once the wind has headed you (shifted
    against your current tack relative to the mean) by more than ``threshold``.

    In steady wind there are no shifts, so this never tacks voluntarily -- it
    sails the long board to the layline. ``threshold`` (deg) is how much header
    you tolerate before flipping: small = twitchy, large = patient.
    """

    name = "tack_on_header"

    def __init__(self, threshold: float = 8.0, mean_tau: float = 90.0) -> None:
        super().__init__(mean_tau)
        self.threshold = float(threshold)

    def decide(self, ctx: StrategyContext) -> bool:
        return self._headed(ctx, update=True) >= self.threshold

    def explain(self, ctx: StrategyContext) -> dict:
        headed = self._headed(ctx, update=False)
        return {
            "rule": "tack when the wind has headed the current tack (vs the mean) "
            "by more than the threshold",
            "mean_wind_deg": round(self.mean_wind, 1) if self.mean_wind is not None else None,
            "current_wind_deg": round(ctx.twd, 1),
            "headed_deg": round(headed, 1),
            "threshold_deg": self.threshold,
        }

    def to_dict(self) -> dict:
        return {"name": self.name, "threshold": self.threshold, "mean_tau": self.mean_tau}


class TackOnLift(_HeaderSense):
    """The classic blunder, kept as a control: tack when you're *lifted* (tack
    onto the header). Should reliably lose to :class:`TackOnHeader` in oscillating
    breeze -- a good sanity check that the model rewards the right behaviour.
    """

    name = "tack_on_lift"

    def __init__(self, threshold: float = 8.0, mean_tau: float = 90.0) -> None:
        super().__init__(mean_tau)
        self.threshold = float(threshold)

    def decide(self, ctx: StrategyContext) -> bool:
        return self._headed(ctx, update=True) <= -self.threshold  # lifted past threshold

    def explain(self, ctx: StrategyContext) -> dict:
        headed = self._headed(ctx, update=False)
        return {
            "rule": "(control) tack when LIFTED past the threshold — i.e. tack "
            "onto the header. Expected to lose.",
            "mean_wind_deg": round(self.mean_wind, 1) if self.mean_wind is not None else None,
            "current_wind_deg": round(ctx.twd, 1),
            "lifted_deg": round(-headed, 1),
            "threshold_deg": self.threshold,
        }

    def to_dict(self) -> dict:
        return {"name": self.name, "threshold": self.threshold, "mean_tau": self.mean_tau}


class TackAtHalfHeader(_HeaderSense):
    """Tack at the halfway point of the header.

    Rather than tacking the instant you're headed (twitchy, lots of tacks) or
    only after a fixed threshold, this waits until the wind has shifted against
    you by ``fraction`` of the oscillation's amplitude -- halfway into the header
    by default. In a clean oscillation that means tacking partway between the
    median heading and the maximum header. Steady wind => no header => never tacks.

    Parameters
    ----------
    amplitude:
        Peak shift each way (deg). Set it to match the breeze (e.g. 12 for a
        +/-12 deg oscillation). Leave ``None`` to estimate it on the fly from the
        observed wind (it converges within about half a cycle).
    fraction:
        Where in the header to pull the trigger: 0.5 = halfway (default), smaller
        tacks earlier (nearer the median), larger waits deeper into the header.
    mean_tau:
        Seconds of smoothing for the running mean-wind estimate.
    """

    name = "tack_at_half_header"

    def __init__(
        self, amplitude: float | None = None, fraction: float = 0.5, mean_tau: float = 90.0
    ) -> None:
        super().__init__(mean_tau)
        self.amplitude = None if amplitude is None else float(amplitude)
        self.fraction = float(fraction)
        self._peak = 0.0

    def reset(self) -> None:
        super().reset()
        self._peak = 0.0

    def decide(self, ctx: StrategyContext) -> bool:
        headed = self._headed(ctx, update=True)
        self._peak = max(self._peak * 0.999, abs(wrap180(ctx.twd - (self.mean_wind or ctx.twd))))
        amp = self.amplitude if self.amplitude is not None else self._peak
        if amp <= 0.1:
            return False
        return headed >= self.fraction * amp

    def explain(self, ctx: StrategyContext) -> dict:
        headed = self._headed(ctx, update=False)
        amp = self.amplitude if self.amplitude is not None else self._peak
        return {
            "rule": "tack when headed >= fraction × amplitude (halfway into the header)",
            "mean_wind_deg": round(self.mean_wind, 1) if self.mean_wind is not None else None,
            "current_wind_deg": round(ctx.twd, 1),
            "headed_deg": round(headed, 1),
            "amplitude_deg": round(amp, 1),
            "trigger_deg": round(self.fraction * amp, 1),
            "fraction": self.fraction,
        }

    def to_dict(self) -> dict:
        d = {"name": self.name, "fraction": self.fraction, "mean_tau": self.mean_tau}
        if self.amplitude is not None:
            d["amplitude"] = self.amplitude
        return d


class FixedInterval(Strategy):
    """Tack/gybe on a fixed clock -- mostly for testing and demonstrations."""

    name = "fixed_interval"

    def __init__(self, period: float = 120.0) -> None:
        self.period = float(period)
        self._next = period

    def reset(self) -> None:
        self._next = self.period

    def decide(self, ctx: StrategyContext) -> bool:
        if ctx.t >= self._next:
            self._next += self.period
            return True
        return False

    def explain(self, ctx: StrategyContext) -> dict:
        return {
            "rule": "tacks every period seconds (clock-based)",
            "period_s": self.period,
            "t_s": round(ctx.t, 1),
        }

    def to_dict(self) -> dict:
        return {"name": self.name, "period": self.period}


_REGISTRY = {
    MinimizeTacks.name: MinimizeTacks,
    TackOnHeader.name: TackOnHeader,
    TackOnLift.name: TackOnLift,
    TackAtHalfHeader.name: TackAtHalfHeader,
    FixedInterval.name: FixedInterval,
}


def strategy_from_dict(d: dict) -> Strategy:
    """Build a strategy from ``{"name": ..., **params}`` (used by scenario load)."""
    params = {k: v for k, v in d.items() if k != "name"}
    return _REGISTRY[d["name"]](**params)
