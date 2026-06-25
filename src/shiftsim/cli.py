"""Command-line entry point.

    python -m shiftsim run SCENARIO.json [--out DIR] [--step SEC] [--quiet]
    python -m shiftsim serve [--port 8000] [--dir .]            # interactive web viewer
    python -m shiftsim polar [--max-speed 8] [--out polar.csv]   # dump a synthetic polar

``run`` prints the comparison table and writes ``replay.json`` (for the web
viewer), ``ladder_gain.svg`` and ``tracks.svg`` into the output dir. ``serve``
starts the interactive viewer where you can edit the wind, boats and tack costs
in the browser and re-run live.
"""
from __future__ import annotations

import argparse
import os
import sys

from .report import ladder_gain_svg, text_report, tracks_svg, write_replay
from .scenario import Scenario


def _cmd_run(args: argparse.Namespace) -> int:
    sc = Scenario.load(args.scenario)
    if args.step is not None:
        sc.run.dt = args.step
    states = sc.run_sim()
    if not args.quiet:
        print(text_report(sc, states))
    out = args.out
    os.makedirs(out, exist_ok=True)
    write_replay(sc, states, os.path.join(out, "replay.json"))
    ladder_gain_svg(states, os.path.join(out, "ladder_gain.svg"))
    tracks_svg(sc, states, os.path.join(out, "tracks.svg"))
    if not args.quiet:
        print(f"\nWrote replay.json, ladder_gain.svg, tracks.svg to {out}/")
        print(f"View the replay: open web/index.html and load {out}/replay.json")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .serve import serve
    serve(directory=os.path.abspath(args.dir), port=args.port)
    return 0


def _cmd_polar(args: argparse.Namespace) -> int:
    from .polar import synthetic_polar
    p = synthetic_polar(max_speed=args.max_speed, pointing=args.pointing)
    header = "twa/tws," + ",".join(str(t) for t in p.tws)
    rows = [header]
    for a, row in zip(p.twa, p.table):
        rows.append(f"{a}," + ",".join(f"{v:.3f}" for v in row))
    text = "\n".join(rows)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print(f"Wrote {args.out}")
    else:
        print(text)
    u = p.best_upwind(10.0); d = p.best_downwind(10.0)
    print(f"\n# at 10kn: best upwind TWA {u[0]:.0f} (VMG {u[1]:.2f}), "
          f"best downwind TWA {d[0]:.0f} (VMG {d[1]:.2f})", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="shiftsim", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a scenario and produce outputs")
    r.add_argument("scenario")
    r.add_argument("--out", default="out", help="output directory (default: out)")
    r.add_argument("--step", type=float, default=None, help="override sim timestep (s)")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(func=_cmd_run)

    s = sub.add_parser("serve", help="start the interactive web viewer")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--dir", default=".", help="directory to serve (default: cwd)")
    s.set_defaults(func=_cmd_serve)

    p = sub.add_parser("polar", help="print/export a synthetic polar")
    p.add_argument("--max-speed", type=float, default=8.0)
    p.add_argument("--pointing", type=float, default=1.0)
    p.add_argument("--out", default=None)
    p.set_defaults(func=_cmd_polar)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
