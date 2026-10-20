"""Exercise publication decisions against real, isolated Git histories."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def git(root: Path, *args: str) -> str:
    """Run Git only in the disposable repository used by these tests."""
    return subprocess.check_output(  # noqa: S603 - arguments are fixed by the tests
        ["git", *args],  # noqa: S607
        cwd=root,
        env={
            "PATH": os.environ["PATH"],
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


@pytest.fixture
def release_repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / "scripts" / "check_release.py",
        tmp_path / "scripts" / "check_release.py",
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "scraper-mcp"\nversion = "1.2.3"\n')
    (tmp_path / "package.json").write_text('{"version": "1.2.3"}')
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "scraper-mcp"\nversion = "1.2.3"\nsource = { editable = "." }\n'
    )
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "release-test@example.invalid")
    git(tmp_path, "config", "user.name", "Release guard test")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "Create a test release.")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tmp_path


def run_guard(
    root: Path, event: str = "push", ref: str = "refs/tags/v1.2.3"
) -> tuple[int, str, str]:
    """Return exit status, diagnostics, and outputs without inheriting credentials."""
    output = root / "github-output"
    result = subprocess.run(
        [sys.executable, "scripts/check_release.py"],
        cwd=root,
        env={
            "PATH": os.environ["PATH"],
            "GITHUB_EVENT_NAME": event,
            "GITHUB_REF": ref,
            "GITHUB_OUTPUT": str(output),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        result.returncode,
        result.stdout + result.stderr,
        output.read_text() if output.exists() else "",
    )


@pytest.mark.parametrize(
    ("event", "ref"),
    [("push", "refs/tags/v1.2.3"), ("workflow_dispatch", "refs/heads/main")],
)
def test_current_main_can_publish(release_repo: Path, event: str, ref: str) -> None:
    code, message, outputs = run_guard(release_repo, event, ref)
    assert code == 0, message
    assert outputs == "version=1.2.3\ncurrent-main=true\n"


@pytest.mark.parametrize(
    ("event", "ref", "error"),
    [
        ("push", "refs/tags/v9.9.9", "Release tag must match"),
        ("push", "refs/tags/v1.2.3-rc1", "Release tag must match"),
        ("workflow_dispatch", "refs/heads/feature/unsafe", "restricted to main"),
        ("pull_request", "refs/heads/main", "requires a version tag or manual dispatch"),
    ],
)
def test_invalid_trigger_cannot_publish(
    release_repo: Path, event: str, ref: str, error: str
) -> None:
    code, message, outputs = run_guard(release_repo, event, ref)
    assert code != 0
    assert error in message
    assert outputs == ""


def test_unmerged_commit_cannot_publish(release_repo: Path) -> None:
    git(release_repo, "commit", "--allow-empty", "-m", "Create an unmerged commit.")
    code, message, outputs = run_guard(release_repo)
    assert code != 0
    assert "must already be merged" in message
    assert outputs == ""


def test_historical_tag_cannot_update_latest(release_repo: Path) -> None:
    release_head = git(release_repo, "rev-parse", "HEAD")
    git(release_repo, "commit", "--allow-empty", "-m", "Advance main beyond this release.")
    git(release_repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(release_repo, "checkout", release_head)
    code, message, outputs = run_guard(release_repo)
    assert code == 0, message
    assert outputs == "version=1.2.3\ncurrent-main=false\n"


@pytest.mark.parametrize(
    ("filename", "contents", "error"),
    [
        ("package.json", '{"version": "0.0.0"}', "Python and dashboard package versions"),
        (
            "uv.lock",
            '[[package]]\nname = "scraper-mcp"\nversion = "0.0.0"\nsource = { editable = "." }\n',
            "uv.lock must contain",
        ),
        ("uv.lock", "package = []\n", "uv.lock must contain"),
        (
            "pyproject.toml",
            '[project]\nname = "scraper-mcp"\nversion = "1.2.3rc1"\n',
            "stable major.minor.patch",
        ),
    ],
)
def test_inconsistent_metadata_cannot_publish(
    release_repo: Path, filename: str, contents: str, error: str
) -> None:
    (release_repo / filename).write_text(contents)
    code, message, outputs = run_guard(release_repo)
    assert code != 0
    assert error in message
    assert outputs == ""
