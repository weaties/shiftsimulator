# Contributing to shiftsim

shiftsim is a sailing-tactics simulator for studying when to tack or gybe in
different wind-shift situations. This guide covers how we work. The model itself
is documented in [`web/docs.html`](web/docs.html) and the engine conventions in
[`CLAUDE.md`](CLAUDE.md).

## Getting started

No dependencies to install — the engine is pure Python standard library.

```bash
git clone git@github.com:weaties/shiftsimulator.git
cd shiftsimulator
python tests/run_all.py                 # run the test suite
python -m shiftsim serve                # interactive viewer at localhost:8000/web/
```

## Development workflow

### Issue → PR lifecycle

1. **Claim the issue**: apply the `in-progress` label and comment which branch:
   ```bash
   gh issue edit <number> --add-label "in-progress"
   gh issue comment <number> --body "In progress on \`<branch-name>\`"
   ```
2. Branch off `main`: `git checkout -b feature/my-feature main`
3. For anything non-trivial (a new wind model, strategy, or ops/deployment work),
   **write a short spec first** in `docs/specs/<name>.md` and link it on the
   issue for review before you build. See `docs/specs/` for the format.
4. Write a failing test, implement, make it pass. Tactical features get an
   *outcome* test (who should win and why); physics changes get an *invariant*
   test. See `tests/` and the `validate-physics` skill.
5. Run all checks (below) before pushing.
6. Push and open a PR targeting `main`.
7. The PR body **must** include `Closes #<issue>` (or `Fixes #<issue>` for bugs)
   so the issue auto-closes on merge.
8. All changes to `main` come through merged PRs — never push directly.

### Required checks

```bash
python tests/run_all.py          # all tests pass

# docs-in-sync: every field tooltip must link to a real docs section
comm -23 <(grep -oE "a:'[a-z-]+'" web/index.html | sed "s/a:'//;s/'//" | sort -u) \
         <(grep -oE 'id="[a-z-]+"' web/docs.html | sed 's/id="//;s/"//' | sort)
# (prints nothing when all anchors resolve)
```

CI (`.github/workflows/ci.yml`) runs both on every push and PR.

### Keep the documentation in sync (required)

This is a hard rule, enforced by CI. Whenever you **add, remove, rename, or
change the meaning of** a parameter, wind model, strategy, metric, or RunConfig
knob, you MUST in the same PR update `web/docs.html` and the matching field
tooltip/anchor in `web/index.html`. See the "Keep the documentation in sync"
section of `CLAUDE.md` for the exact steps. Docs that no longer describe the
behaviour are treated like a failing test.

### Promotion gate

Releases flow `main → stage → live` via the `promote.yml` workflow (added with
the deployment feature). A new `##` heading must exist in `RELEASES.md` for the
promoted commits — write the release note before promoting.

## Coding standards

- **Match the surrounding code.** Dataclasses, type hints, docstrings that
  explain the *sailing* meaning, not just the mechanics.
- **No new runtime dependencies** without discussion — the zero-install,
  pure-stdlib property is a feature (it's how this runs anywhere, including the
  Pi). Optional dev/analysis deps are fine if guarded.
- **Determinism is sacred.** No wall-clock or unseeded randomness in the engine
  (`test_determinism` guards this). Seed any randomness and expose the seed.
- **Don't loosen the safety nets to fix a bad strategy.** If a strategy thrashes
  or DNFs, fix the strategy (add hysteresis), not the simulator's layline /
  thrash-breaker logic.

## Reporting issues

Use the issue templates. Because runs are deterministic, a bug report that
includes the exact scenario settings (or the scenario JSON) is reproducible
one-to-one — please include them.
