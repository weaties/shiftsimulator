"""Deployment status + actions behind the web admin page (``web/admin.html``).

This is the shiftsim analogue of helmlog's ``/admin/deployment``: it reports what
is deployed (running build, the main→stage→live pipeline, promotion history) and
can **deploy** the latest trusted build or **restart** the service.

**Unauthenticated — by explicit owner decision** (see
``docs/specs/admin-page.md``). The page and these endpoints are reachable by
anyone who can open ``/sim/``. The blast radius is bounded by non-auth guardrails,
not by a login:

* **Trusted-branch allowlist** — :func:`deploy` only ever checks out one of
  :data:`TRUSTED_BRANCHES` (the promote-pipeline tiers), never a caller-supplied
  ref, so the worst an anonymous caller can do is redeploy already-trusted code.
* **Single-flight lock** — :data:`_deploy_lock` serialises deploys; a second one
  is refused rather than racing a checkout.
* **No shell** — every privileged call is a fixed ``argv`` to
  :func:`subprocess.run` (never ``shell=True``); the only request-derived value
  is the validated branch name.

Read-only views use plain ``git`` (the deployed tree is world-readable). The
privileged actions (``fetch``/``reset``/``checkout`` on the root-owned
``/opt/shiftsim``, and ``systemctl restart``) go through a scoped ``sudo``
allowlist installed by ``scripts/setup.sh``; off the box they fail cleanly and
only the read-only views work.
"""

from __future__ import annotations

import contextlib
import subprocess
import threading
import time

SERVICE = "shiftsim"
TRACK_DEFAULT = "live"
# Only the promote-pipeline tiers may ever be deployed — these are the refs that
# have already passed PR + CI + promotion. This is the core anti-RCE guard.
TRUSTED_BRANCHES = ("main", "stage", "live")
PIPELINE = ("main", "stage", "live")

# The short SHA each served directory's process started on, captured at startup
# (see :func:`record_startup`). If the code on disk later differs, the page shows
# "restart needed" — a deploy pulled new code but the service hasn't bounced yet.
_startup_sha: dict[str, str] = {}

# Serialises deploys so two clicks can't race a checkout (non-auth guardrail).
_deploy_lock = threading.Lock()


class AdminError(RuntimeError):
    """A deploy/restart action was refused or failed; message is operator-safe."""


# --------------------------------------------------------------------------- #
# git / sudo helpers
# --------------------------------------------------------------------------- #
def _git(directory: str, *args: str, timeout: float = 15) -> str:
    """Run a read-only git command in ``directory`` and return stdout (stripped).

    ``safe.directory`` lets the unprivileged service user read the root-owned
    deploy checkout without git's "dubious ownership" refusal.
    """
    base = ["git", "-C", directory, "-c", f"safe.directory={directory}", "--no-optional-locks"]
    out = subprocess.run(
        base + list(args), capture_output=True, text=True, timeout=timeout, check=True
    )
    return out.stdout.strip()


def _git_or(directory: str, default: str, *args: str) -> str:
    """:func:`_git`, returning ``default`` on any failure (missing ref, no git)."""
    try:
        return _git(directory, *args)
    except Exception:  # noqa: BLE001 — best-effort read for display
        return default


def _count(directory: str, base_ref: str, tip_ref: str) -> int:
    """Number of commits on ``tip_ref`` not on ``base_ref`` (``base..tip``)."""
    out = _git_or(directory, "", "rev-list", "--count", f"{base_ref}..{tip_ref}")
    try:
        return int(out)
    except ValueError:
        return 0


def _sudo_git(directory: str, *args: str, timeout: float = 60) -> None:
    """Run a **privileged** git command (write to the root-owned repo) via sudo.

    Allowed on the box by ``scripts/setup.sh``'s sudoers drop-in; off the box
    ``sudo -n`` fails non-interactively (it never prompts).
    """
    base = [
        "sudo", "-n", "git", "-C", directory,
        "-c", f"safe.directory={directory}", "--no-optional-locks",
    ]  # fmt: skip
    subprocess.run(base + list(args), capture_output=True, text=True, timeout=timeout, check=True)


def _sudo(argv: list[str], timeout: float = 30) -> None:
    subprocess.run(
        ["sudo", "-n", *argv], capture_output=True, text=True, timeout=timeout, check=True
    )


def _fetch(directory: str) -> None:
    """Best-effort refresh of origin refs (privileged; ignored if unavailable)."""
    with contextlib.suppress(Exception):
        _sudo_git(directory, "fetch", "--prune", "origin", timeout=30)


def _disk_sha(directory: str) -> str:
    return _git_or(directory, "unknown", "rev-parse", "--short", "HEAD")


def _service_active() -> bool:
    try:
        out = subprocess.run(
            ["systemctl", "is-active", SERVICE], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() == "active"
    except Exception:  # noqa: BLE001 — no systemd (dev laptop) / not installed
        return False


def record_startup(directory: str) -> None:
    """Remember the SHA on disk at server startup (drives ``restart_needed``)."""
    _startup_sha[directory] = _disk_sha(directory)


def _validate_track(branch: str) -> str:
    if branch not in TRUSTED_BRANCHES:
        raise AdminError(
            f"branch {branch!r} is not allowed; deploy is limited to {', '.join(TRUSTED_BRANCHES)}"
        )
    return branch


# --------------------------------------------------------------------------- #
# read-only views
# --------------------------------------------------------------------------- #
def status(directory: str, track: str = TRACK_DEFAULT) -> dict:
    """Running build, tracked branch, commits-behind, restart-needed, service up."""
    from .serve import version_info  # lazy: avoid a serve<->admin import cycle

    track = _validate_track(track)
    _fetch(directory)
    running = version_info(directory)
    disk = _disk_sha(directory)
    startup = _startup_sha.get(directory, disk)
    return {
        "running": running,
        "disk_sha": disk,
        "track": track,
        "commits_behind": _count(directory, "HEAD", f"origin/{track}"),
        "restart_needed": disk != startup,
        "service_active": _service_active(),
    }


def pipeline(directory: str) -> dict:
    """main/stage/live HEADs + the commit gaps between tiers (read-only)."""
    _fetch(directory)
    branches = {
        tier: {
            "short_sha": _git_or(directory, "—", "rev-parse", "--short", f"origin/{tier}"),
            "message": _git_or(directory, "", "log", "-1", "--format=%s", f"origin/{tier}"),
            "timestamp": _git_or(directory, "", "log", "-1", "--format=%cI", f"origin/{tier}"),
        }
        for tier in PIPELINE
    }
    return {
        "branches": branches,
        "gaps": {
            "main_ahead_of_stage": _count(directory, "origin/stage", "origin/main"),
            "stage_ahead_of_live": _count(directory, "origin/live", "origin/stage"),
        },
    }


def promotions(directory: str, limit: int = 20) -> dict:
    """Recent promotions, read from the ``stage/*`` / ``live/*`` tags."""
    listing = _git_or(directory, "", "tag", "-l", "stage/*", "live/*", "--sort=-creatordate")
    tags = [t for t in listing.splitlines() if t][:limit]
    items = [
        {
            "tag": tag,
            "tier": tag.split("/", 1)[0],
            "short_sha": _git_or(directory, "", "rev-list", "-1", "--abbrev-commit", tag),
            "message": _git_or(directory, "", "log", "-1", "--format=%s", tag),
            "timestamp": _git_or(directory, "", "log", "-1", "--format=%cI", tag),
        }
        for tag in tags
    ]
    return {"promotions": items}


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #
def _schedule_restart(delay: float = 1.0) -> None:
    """Restart the service shortly, so the HTTP response flushes before we're
    killed (``systemctl restart`` tears down this very process)."""

    def _go() -> None:
        time.sleep(delay)
        with contextlib.suppress(Exception):
            _sudo(["systemctl", "restart", SERVICE])

    threading.Thread(target=_go, daemon=True).start()


def deploy(directory: str, branch: str = TRACK_DEFAULT) -> dict:
    """Fetch + hard-reset ``directory`` to ``origin/<branch>`` and restart.

    ``branch`` must be a trusted pipeline tier. Refuses (rather than queues) if a
    deploy is already running.
    """
    branch = _validate_track(branch)
    if not _deploy_lock.acquire(blocking=False):
        raise AdminError("a deploy is already in progress")
    try:
        before = _disk_sha(directory)
        _sudo_git(directory, "fetch", "origin", branch, timeout=120)
        _sudo_git(directory, "reset", "--hard", f"origin/{branch}", timeout=30)
        _sudo_git(directory, "checkout", "-B", branch, f"origin/{branch}", timeout=30)
        after = _disk_sha(directory)
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or str(e)).strip().splitlines()
        raise AdminError(f"deploy failed: {detail[-1] if detail else e}") from e
    finally:
        _deploy_lock.release()
    _schedule_restart()
    return {"status": "ok", "branch": branch, "from": before, "to": after, "restarting": True}


def restart() -> dict:
    """Restart the service (shortly, so this response returns first)."""
    _schedule_restart()
    return {"status": "ok", "restarting": True}
