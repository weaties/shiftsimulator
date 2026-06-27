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
class StartLine:
    """The start line, looking *upwind*: ``committee`` is the starboard (right)
    end, ``pin`` the port (left) end. Boats are placed along it (see
    :func:`place_on_line`) for a start-line situation."""

    committee: Vec  # starboard / right-hand end
    pin: Vec  # port / left-hand end


@dataclass
class Course:
    marks: list[Mark]
    start: Vec = (0.0, 0.0)
    start_line: StartLine | None = None

    def to_dict(self) -> dict:
        d: dict = {
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
        if self.start_line is not None:
            d["start_line"] = {
                "committee": list(self.start_line.committee),
                "pin": list(self.start_line.pin),
            }
        return d

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
        sl = d.get("start_line")
        line = (
            StartLine(committee=tuple(sl["committee"]), pin=tuple(sl["pin"]))
            if sl is not None
            else None
        )
        return cls(marks=marks, start=tuple(d.get("start", (0.0, 0.0))), start_line=line)


def start_line_across(twd: float, length: float, center: Vec = (0.0, 0.0)) -> StartLine:
    """A start line ``length`` metres long, square to the wind, centred on
    ``center``. Looking upwind (toward ``unit(twd)``) the committee end is to the
    right (``unit(twd + 90)``) and the pin to the left."""
    from .geometry import add, scale, unit

    right = unit(twd + 90.0)  # starboard end direction, looking upwind
    return StartLine(
        committee=add(center, scale(right, length / 2.0)),
        pin=add(center, scale(right, -length / 2.0)),
    )


def place_on_line(line: StartLine, fraction: float, behind: float, twd: float) -> Vec:
    """A position ``fraction`` of the way from the **pin (0.0)** to the
    **committee (1.0)** end of ``line``, moved ``behind`` metres to leeward
    (down the ``-unit(twd)`` axis)."""
    from .geometry import add, scale, sub, unit

    along = sub(line.committee, line.pin)
    base = add(line.pin, scale(along, fraction))
    return add(base, scale(unit(twd), -behind))


def windward_leeward(
    beat_length: float = 1000.0, mean_twd: float = 0.0, laps: int = 1, line_length: float = 0.0
) -> Course:
    """A windward-leeward course aligned with ``mean_twd``.

    The windward mark sits ``beat_length`` metres dead upwind of the start
    (i.e. in the direction the wind blows from); the leeward mark sits back at
    the start line. ``laps`` repeats the up/down cycle. When ``line_length > 0``
    a start line of that length is laid across the start, square to the wind.
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
    line = start_line_across(mean_twd, line_length) if line_length > 0 else None
    return Course(marks=marks, start=(0.0, 0.0), start_line=line)
