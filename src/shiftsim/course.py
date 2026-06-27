"""Course geometry: marks and legs.

The built-in :func:`windward_leeward` course is a beat up to a windward mark and
a run back down to a leeward mark, but a :class:`Course` is just an ordered list
of marks, so triangles or custom courses work too.

Each mark carries the *point of sail* used to reach it (``upwind`` or
``downwind``), which is what tells a boat whether it is beating (and tacks) or
running (and gybes) on the way to that mark.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .geometry import Vec


@dataclass
class Mark:
    name: str
    pos: Vec
    point_of_sail: str  # "upwind" or "downwind"
    rounding_radius: float = 15.0  # metres; within this the mark is "rounded"


@dataclass
class Course:
    marks: list[Mark]
    start: Vec = (0.0, 0.0)

    def to_dict(self) -> dict:
        return {
            "start": list(self.start),
            "marks": [
                {
                    "name": m.name,
                    "pos": list(m.pos),
                    "point_of_sail": m.point_of_sail,
                    "rounding_radius": m.rounding_radius,
                }
                for m in self.marks
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Course:
        marks = [
            Mark(
                name=m["name"],
                pos=tuple(m["pos"]),
                point_of_sail=m["point_of_sail"],
                rounding_radius=m.get("rounding_radius", 15.0),
            )
            for m in d["marks"]
        ]
        return cls(marks=marks, start=tuple(d.get("start", (0.0, 0.0))))


def windward_leeward(beat_length: float = 1000.0, mean_twd: float = 0.0, laps: int = 1) -> Course:
    """A windward-leeward course aligned with ``mean_twd``.

    The windward mark sits ``beat_length`` metres dead upwind of the start
    (i.e. in the direction the wind blows from); the leeward mark sits back at
    the start line. ``laps`` repeats the up/down cycle.
    """
    from .geometry import add, scale, unit

    up = unit(mean_twd)  # toward where wind comes from
    wm = add((0.0, 0.0), scale(up, beat_length))
    lm = (0.0, 0.0)
    marks: list[Mark] = []
    for lap in range(laps):
        suffix = "" if laps == 1 else f"-{lap + 1}"
        marks.append(Mark(f"windward{suffix}", wm, "upwind"))
        marks.append(Mark(f"leeward{suffix}", lm, "downwind"))
    return Course(marks=marks, start=(0.0, 0.0))
