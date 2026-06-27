"""Deployment admin actions (web/admin.html backend).

These run with no network and no sudo: they exercise the guardrails (trusted
branch allowlist, single-flight deploy lock) and the read-only status/pipeline/
promotion shapes against the test checkout. The privileged paths (fetch/reset/
restart) are only reachable on the deployed box and are not exercised here.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.admin import (
    TRUSTED_BRANCHES,
    AdminError,
    _deploy_lock,
    _validate_track,
    deploy,
    pipeline,
    promotions,
    status,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_track_allowlist_accepts_trusted() -> None:
    for b in TRUSTED_BRANCHES:
        assert _validate_track(b) == b


def test_track_allowlist_rejects_anything_else() -> None:
    for bad in ["evil; rm -rf /", "origin/main", "HEAD", "", "feature/x", "live "]:
        try:
            _validate_track(bad)
            raise AssertionError(f"should have rejected {bad!r}")
        except AdminError:
            pass


def test_deploy_rejects_untrusted_branch_before_doing_anything() -> None:
    # An arbitrary ref must be refused outright (this is the core RCE guard).
    try:
        deploy(REPO, "feature/sneaky")
        raise AssertionError("should reject untrusted branch")
    except AdminError as e:
        assert "not allowed" in str(e).lower()


def test_deploy_lock_is_single_flight() -> None:
    assert _deploy_lock.acquire(blocking=False)
    try:
        deploy(REPO, "live")  # valid branch, but the lock is held
        raise AssertionError("should refuse while a deploy is in progress")
    except AdminError as e:
        assert "progress" in str(e).lower()
    finally:
        _deploy_lock.release()


def test_status_shape() -> None:
    s = status(REPO)
    for k in ("running", "disk_sha", "track", "commits_behind", "restart_needed", "service_active"):
        assert k in s, f"missing {k}"
    assert isinstance(s["commits_behind"], int)
    assert isinstance(s["restart_needed"], bool)
    assert isinstance(s["service_active"], bool)
    assert set(s["running"]) == {"hostname", "branch", "sha", "dirty"}


def test_pipeline_shape() -> None:
    p = pipeline(REPO)
    assert set(p["branches"]) == {"main", "stage", "live"}
    for info in p["branches"].values():
        assert set(info) == {"short_sha", "message", "timestamp"}
    assert "main_ahead_of_stage" in p["gaps"]
    assert "stage_ahead_of_live" in p["gaps"]
    assert isinstance(p["gaps"]["main_ahead_of_stage"], int)


def test_promotions_shape() -> None:
    pr = promotions(REPO)
    assert isinstance(pr["promotions"], list)
    for item in pr["promotions"]:
        assert set(item) == {"tag", "tier", "short_sha", "message", "timestamp"}
        assert item["tier"] in ("stage", "live")
