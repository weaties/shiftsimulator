# CLAUDE.md — shiftsim

The canonical project guide for all agents (human or AI) lives in `AGENTS.md` —
the model, conventions, and workflow. It is imported here so Claude Code loads it
as project instructions:

@AGENTS.md

Everything in `AGENTS.md` applies. The rest of this file is **only** the
Claude-Code-specific mechanics — keep project conventions in `AGENTS.md`, not here.

## Claude Code specifics

- **Worktrees.** `AGENTS.md`'s "always work in a git worktree" rule is enforced
  here via the **`EnterWorktree`** tool: before any edit, check
  `git worktree list`, then enter an existing worktree if the branch matches,
  otherwise `EnterWorktree` a new one. Read-only work doesn't need one.

- **Project skills.** The harness lists these each session; invoke with the Skill
  tool (`/name`):
  - `/add-wind-scenario` — add a new `WindField` or author a scenario JSON.
  - `/add-boat-strategy` — add a tack/gybe `Strategy` or a boat polar.
  - `/run-compare` — run a matchup and read the comparison output / replay.
  - `/validate-physics` — sanity-check the model after changes.
