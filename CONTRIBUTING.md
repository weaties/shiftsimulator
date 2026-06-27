# Contributing to shiftsim

shiftsim is a sailing-tactics simulator for studying when to tack or gybe in
different wind-shift situations. **The conventions, the model, the workflow, and
the coding standards all live in [`AGENTS.md`](AGENTS.md)** — the single source of
truth for humans and AI agents alike. This file is just the quick start.

## Getting started

The engine is pure Python standard library — nothing to install to run it. `uv`
manages the dev toolchain (ruff, mypy, pytest).

```bash
git clone git@github.com:weaties/shiftsimulator.git
cd shiftsimulator
uv sync                              # install the dev toolchain
uv run python tests/run_all.py       # run the test suite
uv run python -m shiftsim serve      # interactive viewer at localhost:8000/web/
```

(`uv` not installed? See https://docs.astral.sh/uv/. The engine also runs under a
plain `python -m shiftsim …` since it has no runtime dependencies.)

## Then read AGENTS.md

Before opening a PR, read [`AGENTS.md`](AGENTS.md). The essentials:

- **Work on a feature branch via a merged PR** — never push to `main`. Put
  `Closes #N` in the PR body.
- **Keep the docs in sync** (CI-enforced): a field/model change must update
  `web/docs.html` and the matching tooltip/anchor in `web/index.html` in the same
  change.
- **Determinism is sacred** — no unseeded randomness or wall-clock in the engine.
- **Don't loosen the safety nets** to rescue a bad strategy.
- **Run the checks before pushing:**
  ```bash
  uv run python tests/run_all.py
  uv run ruff check . && uv run ruff format --check . && uv run mypy src/
  ```

## Reporting issues

Use the issue templates. Because runs are deterministic, a bug report that
includes the exact scenario settings (or the scenario JSON) reproduces one-to-one
— please include them.
