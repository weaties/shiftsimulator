"""The simulation loop.

All boats are stepped in lockstep against the **same** wind field, so the
recorded histories line up in time and the comparison is fair (identical
conditions, seeded). Each boat is otherwise independent -- there is no collision
or right-of-way model; this is a tactics sandbox, not a fleet-racing sim.

Each step, for every still-racing boat:

1. Read the wind at the boat's time & position.
2. Work out the optimal TWA for the leg and the heading on each tack.
3. Ask the strategy whether to maneuver; if not, check the layline backstop.
4. Apply any maneuver (flip tack, start the speed-recovery penalty).
5. Move at polar speed * maneuver factor, record a sample, check for rounding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .boat import BoatState, Sample
from .geometry import add, bearing_of, dot, norm, scale, sub, unit, wrap180, wrap360
from .strategy import StrategyContext

if TYPE_CHECKING:
    from .course import Course
    from .geometry import Vec
    from .wind import WindField

KN_TO_MS = 0.514444


def heading_for(tack: str, twd: float, twa: float) -> float:
    """Heading sailed on ``tack`` at angle ``twa`` off wind direction ``twd``.

    Port = wind over the left side -> heading = TWD + TWA.
    Starboard = wind over the right side -> heading = TWD - TWA.
    Works for both beating (small TWA) and running (large TWA)."""
    return wrap360(twd + (twa if tack == "port" else -twa))


def other_tack(tack: str) -> str:
    return "starboard" if tack == "port" else "port"


@dataclass
class RunConfig:
    dt: float = 0.5
    max_time: float = 3600.0
    sample_every: int = 2  # record a sample every N steps (replay size)
    fetch_tol: float = 5.0  # deg; how close to the mark bearing counts as "laying" it
    layline_wind_tau: float = 90.0  # s; smoothing for the wind estimate used for laylines
    capture_radius: float = 50.0  # m; round the mark on closest approach within this
    no_maneuver_radius: float = 60.0  # m; inside this only laylines/recovery act, not tactics
    thrash_limit: int = 4  # maneuvers within thrash_window before a boat is
    thrash_window: float = 55.0  # s -- flagged "struggling" and sailed on laylines only


class Simulator:
    def __init__(
        self, wind: WindField, course: Course, ref_twd: float, run: RunConfig | None = None
    ) -> None:
        self.wind = wind
        self.course = course
        self.ref_twd = ref_twd
        self.run = run or RunConfig()
        self._ladder_axis = unit(ref_twd)  # +ve component = toward windward

    def step_boat(self, b: BoatState, t: float, record: bool) -> None:
        if b.finished:
            return
        mark = self.course.marks[b.leg]
        twd, tws = self.wind.at(t, b.pos)

        # slowly-adapting wind estimate used to place stable laylines: smooths
        # oscillations but tracks a persistent trend (see _at_layline).
        ema = getattr(b, "_wind_ema", twd)
        alpha = 1.0 - math.exp(-self.run.dt / max(1e-6, self.run.layline_wind_tau))
        ema = wrap360(ema + alpha * wrap180(twd - ema))
        b._wind_ema = ema  # type: ignore[attr-defined]

        pos_kind = mark.point_of_sail
        if pos_kind == "upwind":
            twa = b.cfg.polar.best_upwind(tws)[0]
        else:
            twa = b.cfg.polar.best_downwind(tws)[0]

        h_cur = heading_for(b.tack, twd, twa)
        h_oth = heading_for(other_tack(b.tack), twd, twa)
        to_mark = sub(mark.pos, b.pos)
        dist = norm(to_mark)
        brg = bearing_of(to_mark)

        # --- decide whether to maneuver -----------------------------------
        can_maneuver = (
            t >= b.maneuver_end and (t - b.last_maneuver_t) >= b.cfg.min_time_between_maneuvers
        )
        do_maneuver = False
        if can_maneuver:
            ctx = StrategyContext(
                t=t,
                dt=self.run.dt,
                point_of_sail=pos_kind,
                tack=b.tack,
                twd=twd,
                tws=tws,
                twa=twa,
                heading_current=h_cur,
                heading_other=h_oth,
                bearing_to_mark=brg,
                dist_to_mark=dist,
            )
            laying, at_layline = self._fetch_state(b, twa, to_mark, brg)
            # Hard safety: if pointing > ~107 deg from the mark the boat has
            # badly overstood. Force a maneuver and enter "recovery" -- the
            # strategy is suppressed until the mark is rounded so a pathological
            # strategy converges (slowly) instead of livelocking.
            sailing_away = dot(unit(h_cur), to_mark) < -0.30
            recovering = getattr(b, "_recovering", False)
            reason = None
            if sailing_away:
                do_maneuver = True
                reason = "sailing_away"
                b._recovering = True  # type: ignore[attr-defined]
            elif recovering:
                do_maneuver = at_layline
                reason = "layline_recovery"
            elif laying:
                do_maneuver = False  # fetch lock: never tack off the layline
            elif dist < self.run.no_maneuver_radius:
                do_maneuver = at_layline  # near the mark, only fetch -- no tactics
                reason = "layline_approach"
            elif b.cfg.strategy.decide(ctx):
                do_maneuver = True
                reason = "strategy"
            elif at_layline:
                do_maneuver = True
                reason = "layline"

        if do_maneuver:
            b.maneuvers.append(self._explain_maneuver(b, t, pos_kind, reason, ctx, twa, tws))
            self._apply_maneuver(b, t, pos_kind)
            h_cur = heading_for(b.tack, twd, twa)  # heading changed

        # --- move ---------------------------------------------------------
        factor = self._maneuver_factor(b, t)
        speed_kn = b.cfg.polar.speed(twa, tws) * factor
        vel = scale(unit(h_cur), speed_kn * KN_TO_MS)
        b.pos = add(b.pos, scale(vel, self.run.dt))

        vmg = dot(vel, unit(brg))  # toward target mark
        ladder = dot(b.pos, self._ladder_axis)  # progress up wind axis

        if record:
            b.history.append(
                Sample(
                    t=round(t + self.run.dt, 3),
                    pos=(round(b.pos[0], 2), round(b.pos[1], 2)),
                    heading=round(h_cur, 1),
                    tack=b.tack,
                    twa=round(twa, 1),
                    twd=round(twd, 2),
                    tws=round(tws, 2),
                    boat_speed=round(speed_kn, 3),
                    vmg=round(vmg, 3),
                    ladder=round(ladder, 2),
                    leg=b.leg,
                    maneuvering=factor < 0.999,
                )
            )

        # --- rounding -----------------------------------------------------
        # Round when inside the rounding radius, or on closest approach within
        # the capture radius (so a boat that passes near but not exactly over
        # the mark still rounds instead of sailing past into a dead end).
        d_now = norm(sub(mark.pos, b.pos))
        prev_d = getattr(b, "_prev_dist", None)
        b._prev_dist = d_now  # type: ignore[attr-defined]
        passed = prev_d is not None and d_now > prev_d and d_now < self.run.capture_radius
        if d_now <= mark.rounding_radius or passed:
            b.leg += 1
            b._prev_dist = None  # type: ignore[attr-defined]
            b._recovering = False  # type: ignore[attr-defined]
            if b.leg >= len(self.course.marks):
                b.finished = True
                b.finish_time = round(t + self.run.dt, 2)

    # -- layline / fetch detection -----------------------------------------
    def _fetch_state(self, b: BoatState, twa: float, to_mark: Vec, brg: float) -> tuple[bool, bool]:
        """Return ``(laying, at_layline)`` for the current target mark.

        Both are judged against the *mean* wind estimate (``_wind_ema``), not
        the momentary direction -- a good tactician lays the mark on the average,
        so an oscillation near the layline doesn't trigger an early/late tack and
        a blown approach.

        * ``laying`` -- the current tack already fetches the mark (heading within
          ``fetch_tol`` of the bearing to it). Used as a "fetch lock": a boat
          that is laying the mark never tacks away from it.
        * ``at_layline`` -- the *other* tack now fetches the mark and the current
          one does not, i.e. we've reached the layline and must maneuver to avoid
          overstanding.
        """
        mean_twd = getattr(b, "_wind_ema", self.ref_twd)
        h_cur_mean = heading_for(b.tack, mean_twd, twa)
        h_oth_mean = heading_for(other_tack(b.tack), mean_twd, twa)
        err_cur = abs(wrap180(h_cur_mean - brg))
        err_oth = abs(wrap180(h_oth_mean - brg))
        tol = self.run.fetch_tol
        ahead_cur = dot(unit(h_cur_mean), to_mark) > 0.0
        ahead_oth = dot(unit(h_oth_mean), to_mark) > 0.0
        laying = err_cur <= tol and ahead_cur
        at_layline = err_oth <= tol and err_oth < err_cur and ahead_oth
        return laying, at_layline

    # -- maneuver explanation (the "show the calculation" feature) ----------
    def _explain_maneuver(
        self,
        b: BoatState,
        t: float,
        pos_kind: str,
        reason: str | None,
        ctx: StrategyContext,
        twa: float,
        tws: float,
    ) -> dict:
        """Build the record of why this tack/gybe happened and the numbers
        behind it, for the web viewer's per-maneuver calculation panel."""
        ec = round(ctx.err(ctx.heading_current), 1)
        eo = round(ctx.err(ctx.heading_other), 1)
        if reason == "strategy":
            expl = b.cfg.strategy.explain(ctx)
        elif reason and reason.startswith("layline"):
            note = {
                "layline": "reached the layline",
                "layline_approach": "reached the layline (near the mark — tactics off)",
                "layline_recovery": "reached the layline (recovering after overstanding)",
            }[reason]
            expl = {
                "rule": f"{note}: the other tack now fetches the mark",
                "err_other_to_mark_deg": eo,
                "fetch_tol_deg": self.run.fetch_tol,
            }
        elif reason == "sailing_away":
            expl = {
                "rule": "overstood — heading was >107 deg from the mark; forced maneuver + recovery"
            }
        else:
            expl = {}
        # approximate distance given up to the maneuver: lost speed integrated
        # over the recovery time (avg speed factor = (msf+1)/2).
        v = b.cfg.polar.speed(twa, tws) * KN_TO_MS
        dist_lost = v * b.cfg.maneuver_time * (1.0 - (b.cfg.maneuver_speed_factor + 1.0) / 2.0)
        return {
            "t": round(t, 1),
            "leg": b.leg,
            "kind": "tack" if pos_kind == "upwind" else "gybe",
            "from": b.tack,
            "to": other_tack(b.tack),
            "reason": reason,
            "twd": round(ctx.twd, 1),
            "tws": round(ctx.tws, 2),
            "bearing_to_mark_deg": round(ctx.bearing_to_mark, 1),
            "err_current_deg": ec,
            "err_other_deg": eo,
            "approx_distance_lost_m": round(dist_lost, 1),
            "maneuver_time_s": b.cfg.maneuver_time,
            "maneuver_speed_factor": b.cfg.maneuver_speed_factor,
            "explain": expl,
        }

    # -- maneuver mechanics ------------------------------------------------
    def _apply_maneuver(self, b: BoatState, t: float, pos_kind: str) -> None:
        b.tack = other_tack(b.tack)
        b.maneuver_end = t + b.cfg.maneuver_time
        b.last_maneuver_t = t
        if pos_kind == "upwind":
            b.n_tacks += 1
        else:
            b.n_gybes += 1
        # thrash breaker: a flurry of maneuvers means the strategy is fighting
        # the layline safety net (a pathological tactic). Suppress the strategy
        # until the next mark so the boat at least finishes (it still loses).
        recent = [x for x in getattr(b, "_maneuver_times", []) if x >= t - self.run.thrash_window]
        recent.append(t)
        b._maneuver_times = recent  # type: ignore[attr-defined]
        if len(recent) >= self.run.thrash_limit:
            b._recovering = True  # type: ignore[attr-defined]
            b.n_struggled += 1

    def _maneuver_factor(self, b: BoatState, t: float) -> float:
        if t >= b.maneuver_end:
            return 1.0
        msf = b.cfg.maneuver_speed_factor
        frac = (t - b.last_maneuver_t) / max(1e-6, b.cfg.maneuver_time)
        return msf + (1.0 - msf) * max(0.0, min(1.0, frac))


def simulate(
    boats: list[BoatState],
    wind: WindField,
    course: Course,
    ref_twd: float,
    run: RunConfig | None = None,
) -> None:
    """Run all boats to completion (or ``max_time``), recording histories
    in-place on each :class:`BoatState`."""
    sim = Simulator(wind, course, ref_twd, run)
    rc = sim.run
    for b in boats:
        b.cfg.strategy.reset()
        b._prev_dist = None  # type: ignore[attr-defined]
        b._recovering = False  # type: ignore[attr-defined]
        b._maneuver_times = []  # type: ignore[attr-defined]
        # seed an initial sample so replays start at the line
        twd, tws = wind.at(0.0, b.pos)
        b._wind_ema = twd  # type: ignore[attr-defined]
        b.history.append(
            Sample(
                t=0.0,
                pos=(round(b.pos[0], 2), round(b.pos[1], 2)),
                heading=heading_for(b.tack, twd, b.cfg.polar.best_upwind(tws)[0]),
                tack=b.tack,
                twa=b.cfg.polar.best_upwind(tws)[0],
                twd=round(twd, 2),
                tws=round(tws, 2),
                boat_speed=0.0,
                vmg=0.0,
                ladder=round(dot(b.pos, sim._ladder_axis), 2),
                leg=0,
                maneuvering=False,
            )
        )

    n_steps = int(math.ceil(rc.max_time / rc.dt))
    for i in range(n_steps):
        t = i * rc.dt
        record = i % rc.sample_every == 0
        if all(b.finished for b in boats):
            break
        for b in boats:
            sim.step_boat(b, t, record)
