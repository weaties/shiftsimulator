"""Scenarios: the reproducible unit of an experiment.

A scenario bundles a wind field, a course, a run config and a list of boats into
one JSON file. Loading + running the same file always produces the same result
(everything is seeded), so a scenario *is* the experiment -- check it in, share
it, diff it.

See ``scenarios/*.json`` for examples and the ``run-compare`` skill for the
workflow around running one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .boat import BoatConfig, BoatState
from .course import Course, place_on_line, windward_leeward
from .polar import Polar, synthetic_polar
from .simulator import RunConfig, simulate
from .strategy import strategy_from_dict
from .wind import WindField, wind_from_dict

if TYPE_CHECKING:
    from .geometry import Vec


def polar_from_dict(d: dict) -> Polar:
    """Build a polar from a scenario block.

    Forms: ``{"type": "synthetic", ...params}``, ``{"type": "csv", "path": ...}``
    or a full inline polar dict (``twa``/``tws``/``table``)."""
    t = d.get("type")
    if t == "synthetic":
        return synthetic_polar(**{k: v for k, v in d.items() if k != "type"})
    if t == "csv":
        return Polar.from_csv(d["path"], name=d.get("name", ""))
    return Polar.from_dict(d)


def boat_from_dict(d: dict) -> BoatConfig:
    return BoatConfig(
        name=d["name"],
        polar=polar_from_dict(d.get("polar", {"type": "synthetic"})),
        strategy=strategy_from_dict(d["strategy"]),
        maneuver_time=d.get("maneuver_time", 12.0),
        maneuver_speed_factor=d.get("maneuver_speed_factor", 0.45),
        min_time_between_maneuvers=d.get("min_time_between_maneuvers", 8.0),
        initial_tack=d.get("initial_tack", "starboard"),
        color=d.get("color", "#1f77b4"),
        length=d.get("length", 6.0),
        beam=d.get("beam", 2.0),
    )


def course_from_dict(d: dict, ref_twd: float) -> Course:
    if d.get("type") == "windward_leeward":
        return windward_leeward(
            beat_length=d.get("beat_length", 1000.0),
            mean_twd=ref_twd,
            laps=d.get("laps", 1),
            line_length=d.get("line_length", 0.0),
        )
    return Course.from_dict(d)


def start_pos(boat_dict: dict, course: Course, ref_twd: float) -> Vec:
    """Where a boat begins. With a start line and a ``start`` placement block
    (``{"line_pos", "behind"}``) the boat is set on the line; otherwise it starts
    at ``course.start`` (the historical behaviour)."""
    s = boat_dict.get("start")
    if s is not None and course.start_line is not None:
        return place_on_line(
            course.start_line, s.get("line_pos", 0.5), s.get("behind", 0.0), ref_twd
        )
    return course.start


@dataclass
class Scenario:
    name: str
    wind: WindField
    course: Course
    boats: list[BoatConfig]
    ref_twd: float = 0.0
    run: RunConfig = field(default_factory=RunConfig)
    description: str = ""
    starts: list[Vec] = field(default_factory=list)  # per-boat start position

    @classmethod
    def from_dict(cls, d: dict) -> Scenario:
        ref_twd = d.get("ref_twd", 0.0)
        run = RunConfig(**d.get("run", {}))
        course = course_from_dict(d.get("course", {"type": "windward_leeward"}), ref_twd)
        return cls(
            name=d.get("name", "scenario"),
            description=d.get("description", ""),
            wind=wind_from_dict(d["wind"]),
            course=course,
            boats=[boat_from_dict(b) for b in d["boats"]],
            ref_twd=ref_twd,
            run=run,
            starts=[start_pos(b, course, ref_twd) for b in d["boats"]],
        )

    @classmethod
    def load(cls, path: str) -> Scenario:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def run_sim(self) -> list[BoatState]:
        """Instantiate fresh boat states (on the start line if placed) and run."""
        states = [
            BoatState(cfg=c, pos=pos, tack=c.initial_tack)
            for c, pos in zip(self.boats, self._start_positions(), strict=False)
        ]
        simulate(states, self.wind, self.course, self.ref_twd, self.run)
        return states

    def _start_positions(self) -> list[Vec]:
        if self.starts:
            return self.starts
        return [self.course.start] * len(self.boats)
