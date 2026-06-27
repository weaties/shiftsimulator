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

from .boat import BoatConfig, BoatState
from .course import Course, windward_leeward
from .polar import Polar, synthetic_polar
from .simulator import RunConfig, simulate
from .strategy import strategy_from_dict
from .wind import WindField, wind_from_dict


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
    )


def course_from_dict(d: dict, ref_twd: float) -> Course:
    if d.get("type") == "windward_leeward":
        return windward_leeward(
            beat_length=d.get("beat_length", 1000.0), mean_twd=ref_twd, laps=d.get("laps", 1)
        )
    return Course.from_dict(d)


@dataclass
class Scenario:
    name: str
    wind: WindField
    course: Course
    boats: list[BoatConfig]
    ref_twd: float = 0.0
    run: RunConfig = field(default_factory=RunConfig)
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> Scenario:
        ref_twd = d.get("ref_twd", 0.0)
        run = RunConfig(**d.get("run", {}))
        return cls(
            name=d.get("name", "scenario"),
            description=d.get("description", ""),
            wind=wind_from_dict(d["wind"]),
            course=course_from_dict(d.get("course", {"type": "windward_leeward"}), ref_twd),
            boats=[boat_from_dict(b) for b in d["boats"]],
            ref_twd=ref_twd,
            run=run,
        )

    @classmethod
    def load(cls, path: str) -> Scenario:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def run_sim(self) -> list[BoatState]:
        """Instantiate fresh boat states at the start line and simulate them."""
        states = [BoatState(cfg=c, pos=self.course.start, tack=c.initial_tack) for c in self.boats]
        simulate(states, self.wind, self.course, self.ref_twd, self.run)
        return states
