"""Boat configuration and live state.

A boat sails at its polar-optimal angle off the wind for the current leg
(upwind or downwind) on one tack at a time. When the wind shifts, the boat
keeps the **same TWA** and so its heading rotates with the wind -- this is what
makes a shift a "lift" or a "header" and is the whole reason tactics matter.

A :class:`Strategy` decides *when* to flip tacks. Flipping costs time: during a
maneuver the boat's speed is knocked down and recovers over ``maneuver_time``
seconds, which is the price every extra tack/gybe pays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .geometry import Vec
    from .polar import Polar
    from .strategy import Strategy


@dataclass
class BoatConfig:
    """Everything that defines how a boat behaves. Fully serialisable."""

    name: str
    polar: Polar
    strategy: Strategy
    maneuver_time: float = 12.0  # seconds to recover from a tack/gybe
    maneuver_speed_factor: float = 0.45  # speed multiplier at the worst of a maneuver
    min_time_between_maneuvers: float = 8.0  # debounce so a boat can't flip every step
    initial_tack: str = "starboard"  # which tack to start the first beat on
    color: str = "#1f77b4"  # for the web replay / charts
    length: float = 6.0  # LOA (m); sets the bad-air shadow reach and the glyph size
    beam: float = 2.0  # max beam (m); the boat's drawn footprint


@dataclass
class Sample:
    """One recorded instant of a boat's run (drives metrics and the replay)."""

    t: float
    pos: Vec
    heading: float
    tack: str
    twa: float
    twd: float
    tws: float
    boat_speed: float
    vmg: float  # made-good toward the current target mark
    ladder: float  # progress up the wind axis (for ladder-rung gains)
    leg: int
    maneuvering: bool
    wind_mult: float = 1.0  # local TWS multiplier from bad air (1.0 = clean air)


@dataclass
class BoatState:
    """Mutable per-run state, separate from the (reusable) config."""

    cfg: BoatConfig
    pos: Vec
    tack: str
    leg: int = 0
    maneuver_end: float = -1.0  # t until which the boat is recovering
    last_maneuver_t: float = -1e9
    n_tacks: int = 0
    n_gybes: int = 0
    n_struggled: int = 0  # times the thrash-breaker had to rescue the boat
    finished: bool = False
    finish_time: float | None = None
    history: list[Sample] = field(default_factory=list)
    maneuvers: list[dict] = field(default_factory=list)  # the why+numbers of each tack/gybe

    @property
    def maneuvering_at(self) -> float:
        return self.maneuver_end
