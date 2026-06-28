"""The bad-air (wind-shadow) model -- the first boat-on-boat interaction.

A boat disturbs the air to **leeward and astern**: a wedge of "dirty air" blown
downwind that robs the boats behind it of wind. We model that wedge as a cone
whose centreline is the **true-wind downwind direction** (``twd + 180``) from the
casting boat -- true wind, not apparent, so the shadow is deterministic and
seed-free (and within a few degrees of apparent at these speeds). Downwind of an
upwind boat *is* aft-and-to-leeward, so a single downwind cone captures both.

A boat inside the cone sees a reduced true wind speed and therefore sails slower
(via the polar); the model does **not** bend the wind direction in this version
(the lee-bow effect is a documented follow-up). "Tack for clear air" is then a
*tactical* choice you study by re-running with a different tack/strategy -- which
is exactly the start-line "alternative reaction" use case.

The model is pure geometry: :func:`shadow_loss` is the fraction of wind a single
caster removes at a point, and :func:`shadow_multipliers` combines every boat's
shadow into a per-boat wind multiplier. It is **order-independent** -- each
multiplier depends only on the boats' positions, so the simulator can compute the
whole vector from a start-of-step snapshot and stay deterministic regardless of
the order boats are stepped in.

See ``docs/specs/start-line.md`` and the ``#bad-air`` section of ``web/docs.html``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import Vec, dot, norm, scale, sub, unit


@dataclass
class BadAirParams:
    """Tunables for the wind-shadow model (mirrors the ``badair_*`` knobs on
    :class:`~shiftsim.simulator.RunConfig`)."""

    enabled: bool = False
    length: float = 8.0  # shadow reach in boat lengths
    half_angle: float = 12.0  # cone half-angle, degrees
    max_loss: float = 0.40  # max fractional TWS loss, at the caster's transom
    cap: float = 0.85  # max combined loss -- a boat is never fully becalmed


def shadow_loss(
    caster_pos: Vec, caster_len: float, victim_pos: Vec, twd: float, p: BadAirParams
) -> float:
    """Fraction of true wind (``0..max_loss``) the caster removes at ``victim_pos``.

    Zero unless the victim is genuinely **downwind** of the caster, within the
    reach (``length`` boat-lengths) and inside the cone. Falls off linearly with
    along-wind distance and lateral offset from the centreline."""
    reach = p.length * caster_len
    if reach <= 0.0:
        return 0.0
    d = unit(twd + 180.0)  # downwind: the way the wind blows TO
    rel = sub(victim_pos, caster_pos)
    along = dot(rel, d)
    if along <= 0.0 or along >= reach:
        return 0.0  # upwind/abeam, or past the end of the shadow
    cross = norm(sub(rel, scale(d, along)))  # perpendicular offset from centreline
    half_width = 0.5 * caster_len + along * math.tan(math.radians(p.half_angle))
    if cross >= half_width:
        return 0.0  # outside the cone
    f_along = 1.0 - along / reach
    f_cross = 1.0 - cross / half_width
    return p.max_loss * f_along * f_cross


def shadow_multipliers(boats: list[tuple[Vec, float, float]], p: BadAirParams) -> list[float]:
    """Per-boat wind multiplier (``1.0`` = clean, ``< 1`` = gassed).

    ``boats`` is ``[(pos, length, twd_at_pos), ...]``. Each boat's loss is the
    independent combination of every *other* boat's shadow, ``1 - prod(1 - loss)``,
    capped at ``p.cap`` so a boat is never fully becalmed (a movement safety net,
    not a tuning knob). Order-independent: depends only on positions."""
    n = len(boats)
    if not p.enabled or n < 2:
        return [1.0] * n
    mults = []
    for i, (vpos, _vlen, _vtwd) in enumerate(boats):
        keep = 1.0
        for j, (cpos, clen, ctwd) in enumerate(boats):
            if i == j:
                continue
            keep *= 1.0 - shadow_loss(cpos, clen, vpos, ctwd, p)
        total = min(p.cap, 1.0 - keep)
        mults.append(1.0 - total)
    return mults
