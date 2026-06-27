"""The /api/version build stamp.

`version_info(directory)` reports the running build (branch, short SHA, dirty
flag, hostname) from git, and must degrade gracefully outside a checkout so the
endpoint can never 500 the viewer.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shiftsim.serve import version_info

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_version_info_shape() -> None:
    info = version_info(REPO)
    assert set(info) == {"hostname", "branch", "sha", "dirty"}
    assert isinstance(info["hostname"], str) and info["hostname"]
    assert isinstance(info["branch"], str) and info["branch"]
    assert isinstance(info["sha"], str) and info["sha"]
    assert isinstance(info["dirty"], bool)


def test_version_info_real_checkout_has_sha() -> None:
    # The test runs inside the git checkout, so we get a real branch/sha,
    # not the "unknown" fallback.
    info = version_info(REPO)
    assert info["sha"] != "unknown"
    assert info["branch"] != "unknown"
    # short SHA is hex and reasonably short
    assert all(c in "0123456789abcdef" for c in info["sha"])
    assert 4 <= len(info["sha"]) <= 12


def test_version_info_non_git_dir_degrades() -> None:
    with tempfile.TemporaryDirectory() as d:
        info = version_info(d)
    assert set(info) == {"hostname", "branch", "sha", "dirty"}
    assert info["branch"] == "unknown"
    assert info["sha"] == "unknown"
    assert info["dirty"] is False
    assert isinstance(info["hostname"], str) and info["hostname"]


def test_version_info_missing_dir_degrades() -> None:
    # A path that doesn't exist must not raise.
    info = version_info("/no/such/path/shiftsim-xyz")
    assert info["sha"] == "unknown"
    assert info["dirty"] is False
