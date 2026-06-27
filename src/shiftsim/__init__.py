"""shiftsim -- a sailing tactics simulator for studying when to tack or gybe.

Quick start (programmatic)::

    from shiftsim.scenario import Scenario
    from shiftsim.report import text_report
    sc = Scenario.load("scenarios/oscillating_demo.json")
    states = sc.run_sim()
    print(text_report(sc, states))

Or from the shell::

    python -m shiftsim run scenarios/oscillating_demo.json --out out/

See CLAUDE.md for the model, conventions, and the project skills.
"""

from .scenario import Scenario  # noqa: F401

__all__ = ["Scenario"]
__version__ = "0.1.0"
