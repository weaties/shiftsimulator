"""Outputs: a text table, self-contained SVG charts, and the replay JSON.

No third-party libraries -- the charts are SVG written by hand and the animated
replay is driven by a JSON file that ``web/index.html`` loads. So the full
analysis (numbers + charts + replay) runs anywhere Python does, with nothing to
install.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .metrics import ladder_gain_series, rank, summarize

if TYPE_CHECKING:
    from .boat import BoatState
    from .scenario import Scenario

# --- text -----------------------------------------------------------------


def text_report(scenario: Scenario, states: list[BoatState]) -> str:
    results = [summarize(b) for b in states]
    ranked = rank(results)
    lines = [f"Scenario: {scenario.name}"]
    if scenario.description:
        lines.append(f"  {scenario.description}")
    lines.append("")
    hdr = (
        f"{'#':>2}  {'boat':<22}{'finish':>9}{'tacks':>7}{'gybes':>7}"
        f"{'dist(m)':>9}{'up VMG':>8}{'ladder':>9}"
    )
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for i, r in enumerate(ranked, 1):
        fin = f"{r.finish_time:.0f}s" if r.finished else "DNF"
        lines.append(
            f"{i:>2}  {r.name:<22}{fin:>9}{r.n_tacks:>7}{r.n_gybes:>7}"
            f"{r.distance_sailed:>9.0f}{r.avg_upwind_vmg:>8.2f}{r.final_ladder:>9.0f}"
        )
    # head-to-head vs winner
    if len(ranked) > 1 and ranked[0].finished and ranked[0].finish_time:
        lines.append("")
        win = ranked[0]
        for r in ranked[1:]:
            if r.finished and r.finish_time is not None and win.finish_time is not None:
                d = r.finish_time - win.finish_time
                lines.append(f"  {win.name} beats {r.name} by {d:.0f}s")
    return "\n".join(lines)


# --- replay JSON ----------------------------------------------------------


def replay_data(scenario: Scenario, states: list[BoatState]) -> dict:
    xs = [s.pos[0] for b in states for s in b.history]
    ys = [s.pos[1] for b in states for s in b.history]
    for m in scenario.course.marks:
        xs.append(m.pos[0])
        ys.append(m.pos[1])
    pad = 80.0
    bounds = {
        "minx": min(xs) - pad,
        "maxx": max(xs) + pad,
        "miny": min(ys) - pad,
        "maxy": max(ys) + pad,
    }
    boats = []
    for b in states:
        boats.append(
            {
                "name": b.cfg.name,
                "color": b.cfg.color,
                "finish_time": b.finish_time,
                "n_tacks": b.n_tacks,
                "n_gybes": b.n_gybes,
                "n_struggled": b.n_struggled,
                "maneuver_time": b.cfg.maneuver_time,
                "maneuver_speed_factor": b.cfg.maneuver_speed_factor,
                "strategy": b.cfg.strategy.to_dict(),
                "maneuvers": b.maneuvers,
                "frames": [
                    {
                        "t": s.t,
                        "x": s.pos[0],
                        "y": s.pos[1],
                        "hdg": s.heading,
                        "tack": s.tack,
                        "man": s.maneuvering,
                        "twd": s.twd,
                        "tws": s.tws,
                        "spd": s.boat_speed,
                        "lad": s.ladder,
                    }
                    for s in b.history
                ],
            }
        )
    return {
        "name": scenario.name,
        "description": scenario.description,
        "ref_twd": scenario.ref_twd,
        "bounds": bounds,
        "course": scenario.course.to_dict(),
        "boats": boats,
        "results": [vars(summarize(b)) for b in states],
        "ladder_gain": ladder_gain_series(states),
    }


def write_replay(scenario: Scenario, states: list[BoatState], path: str) -> None:
    with open(path, "w") as f:
        json.dump(replay_data(scenario, states), f)


# --- SVG charts -----------------------------------------------------------


def _svg_open(w: int, h: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="12">',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
    ]


def ladder_gain_svg(
    states: list[BoatState], path: str, reference: int = 0, w: int = 720, h: int = 380
) -> None:
    """Line chart of ladder-rung gain vs the reference boat over time."""
    data = ladder_gain_series(states, reference=reference)
    times, series = data["times"], data["series"]
    vals = [v for s in series.values() for v in s if v is not None]
    lo, hi = (min(vals), max(vals)) if vals else (-1, 1)
    if hi - lo < 1:
        lo, hi = lo - 1, hi + 1
    m = 50
    pw, ph = w - 2 * m, h - 2 * m
    tmax = times[-1] if times else 1

    def X(t: float) -> float:
        return m + pw * (t / tmax if tmax else 0)

    def Y(v: float) -> float:
        return m + ph * (1 - (v - lo) / (hi - lo))

    out = _svg_open(w, h)
    out.append(
        f'<text x="{w / 2}" y="22" text-anchor="middle" font-size="15" '
        f'font-weight="bold">Ladder-rung gain vs {data["reference"]}</text>'
    )
    # axes
    out.append(f'<line x1="{m}" y1="{Y(0)}" x2="{m + pw}" y2="{Y(0)}" stroke="#bbb"/>')
    out.append(f'<line x1="{m}" y1="{m}" x2="{m}" y2="{m + ph}" stroke="#888"/>')
    out.append(f'<text x="{m - 8}" y="{Y(hi)}" text-anchor="end">{hi:.0f}m</text>')
    out.append(f'<text x="{m - 8}" y="{Y(lo)}" text-anchor="end">{lo:.0f}m</text>')
    out.append(f'<text x="{m - 8}" y="{Y(0) + 4}" text-anchor="end">0</text>')
    out.append(f'<text x="{m + pw}" y="{m + ph + 20}" text-anchor="end">{tmax:.0f}s</text>')
    colors = {b.cfg.name: b.cfg.color for b in states}
    legend_y = m
    for name, ys in series.items():
        pts = [f"{X(t):.1f},{Y(v):.1f}" for t, v in zip(times, ys, strict=False) if v is not None]
        if pts:
            out.append(
                f'<polyline fill="none" stroke="{colors[name]}" '
                f'stroke-width="2" points="{" ".join(pts)}"/>'
            )
        out.append(
            f'<rect x="{m + pw - 120}" y="{legend_y - 9}" width="10" height="10" '
            f'fill="{colors[name]}"/>'
        )
        out.append(f'<text x="{m + pw - 105}" y="{legend_y}">{name}</text>')
        legend_y += 16
    out.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(out))


def tracks_svg(
    scenario: Scenario, states: list[BoatState], path: str, w: int = 560, h: int = 720
) -> None:
    """Top-down plot of the course and each boat's track through the water."""
    b = replay_data(scenario, states)["bounds"]
    bw, bh = b["maxx"] - b["minx"], b["maxy"] - b["miny"]
    m = 30
    sx = (w - 2 * m) / bw if bw else 1
    sy = (h - 2 * m) / bh if bh else 1
    s = min(sx, sy)

    def X(x: float) -> float:
        return m + (x - b["minx"]) * s

    def Y(y: float) -> float:
        return h - m - (y - b["miny"]) * s  # north is up

    out = _svg_open(w, h)
    out.append(
        f'<text x="{w / 2}" y="20" text-anchor="middle" font-size="15" '
        f'font-weight="bold">Tracks &#8212; {scenario.name}</text>'
    )
    # wind arrow (blows FROM ref_twd, toward course)
    from .geometry import unit

    wf = unit((scenario.ref_twd + 180) % 360)
    ax, ay = w - 55, 55
    out.append(
        f'<line x1="{ax - wf[0] * 22}" y1="{ay + wf[1] * 22}" x2="{ax + wf[0] * 22}" '
        f'y2="{ay - wf[1] * 22}" stroke="#3a7" stroke-width="3" '
        f'marker-end="url(#a)"/>'
    )
    out.append(
        '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="6" '
        'refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#3a7"/>'
        "</marker></defs>"
    )
    out.append(f'<text x="{ax}" y="{ay + 38}" text-anchor="middle" fill="#3a7">wind</text>')
    # marks
    for mk in scenario.course.marks:
        out.append(
            f'<circle cx="{X(mk.pos[0]):.1f}" cy="{Y(mk.pos[1]):.1f}" r="5" '
            f'fill="#e63" stroke="#900"/>'
        )
        out.append(f'<text x="{X(mk.pos[0]) + 8:.1f}" y="{Y(mk.pos[1]):.1f}">{mk.name}</text>')
    # tracks
    for bo in states:
        pts = [f"{X(p.pos[0]):.1f},{Y(p.pos[1]):.1f}" for p in bo.history]
        out.append(
            f'<polyline fill="none" stroke="{bo.cfg.color}" stroke-width="1.6" '
            f'opacity="0.9" points="{" ".join(pts)}"/>'
        )
    out.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(out))
