"""Turn recorded boat histories into comparable numbers.

The headline metric is **ladder-rung gain**: how far ahead/behind a boat is up
the wind axis versus a reference boat at the same instant. That is the quantity
that explains *why* one tactic beats another -- you can watch the gap open up on
exactly the shift where the smart boat tacked and the other didn't.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .boat import BoatState, Sample


@dataclass
class BoatResult:
    name: str
    finished: bool
    finish_time: float | None
    n_tacks: int
    n_gybes: int
    distance_sailed: float  # metres through the water
    avg_upwind_vmg: float  # m/s, upwind legs only
    final_ladder: float
    color: str


def _distance(h: list[Sample]) -> float:
    d = 0.0
    for a, b in zip(h, h[1:], strict=False):
        d += ((a.pos[0] - b.pos[0]) ** 2 + (a.pos[1] - b.pos[1]) ** 2) ** 0.5
    return d


def summarize(boat: BoatState) -> BoatResult:
    h = boat.history
    # upwind legs identified by sailing angle (beating uses TWA < 90)
    up = [s.vmg for s in h if s.twa < 90 and s.boat_speed > 0]
    avg_up = sum(up) / len(up) if up else 0.0
    return BoatResult(
        name=boat.cfg.name,
        finished=boat.finished,
        finish_time=boat.finish_time,
        n_tacks=boat.n_tacks,
        n_gybes=boat.n_gybes,
        distance_sailed=round(_distance(h), 1),
        avg_upwind_vmg=round(avg_up, 3),
        final_ladder=round(h[-1].ladder, 1) if h else 0.0,
        color=boat.cfg.color,
    )


def ladder_at_times(boat: BoatState, times: list[float]) -> list[float | None]:
    """Sample a boat's ladder position at the given times (step interpolation)."""
    h = boat.history
    out: list[float | None] = []
    j = 0
    for t in times:
        while j + 1 < len(h) and h[j + 1].t <= t:
            j += 1
        if h[j].t <= t and (boat.finished or t <= h[-1].t):
            out.append(h[j].ladder)
        else:
            out.append(None)
    return out


def common_time_grid(boats: list[BoatState], step: float = 5.0) -> list[float]:
    end = max((b.history[-1].t for b in boats if b.history), default=0.0)
    n = int(end / step) + 1
    return [round(i * step, 2) for i in range(n + 1)]


def ladder_gain_series(boats: list[BoatState], reference: int = 0, step: float = 5.0) -> dict:
    """Ladder-rung gain of every boat relative to ``boats[reference]``.

    Returns ``{"times": [...], "series": {name: [gain_or_None, ...]}}`` where a
    positive value means that boat is that many metres further up the course
    than the reference boat at that time."""
    times = common_time_grid(boats, step)
    ref = ladder_at_times(boats[reference], times)
    series: dict[str, list[float | None]] = {}
    for b in boats:
        lad = ladder_at_times(b, times)
        series[b.cfg.name] = [
            round(x - r, 2) if (x is not None and r is not None) else None
            for x, r in zip(lad, ref, strict=False)
        ]
    return {"times": times, "series": series, "reference": boats[reference].cfg.name}


def rank(results: list[BoatResult]) -> list[BoatResult]:
    """Sort boats best-first: finishers by time, then by distance up the course."""

    def key(r: BoatResult) -> tuple[int, float]:
        return (
            (0, r.finish_time) if r.finished and r.finish_time is not None else (1, -r.final_ladder)
        )

    return sorted(results, key=key)
