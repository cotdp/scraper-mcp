"""Reject image publication from unmerged commits or mismatched version tags."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from pathlib import Path


def main() -> None:
    """Validate the checked-out release and emit safe workflow outputs."""
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]
    version = project["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise SystemExit("Publication requires a stable major.minor.patch project version.")

    dashboard_version = json.loads((root / "package.json").read_text())["version"]
    if dashboard_version != version:
        raise SystemExit("Python and dashboard package versions must match before publication.")

    with (root / "uv.lock").open("rb") as file:
        packages = tomllib.load(file)["package"]
    locked_versions = [
        package.get("version")
        for package in packages
        if package.get("name") == project["name"]
        and package.get("source", {}).get("editable") == "."
    ]
    if locked_versions != [version]:
        raise SystemExit(
            "uv.lock must contain the matching root project version before publication."
        )

    event = os.environ.get("GITHUB_EVENT_NAME")
    ref = os.environ.get("GITHUB_REF")
    if event == "push":
        if ref != f"refs/tags/v{version}":
            raise SystemExit(f"Release tag must match project version: v{version}.")
    elif event == "workflow_dispatch":
        if ref != "refs/heads/main":
            raise SystemExit("Manual image publication is restricted to main.")
    else:
        raise SystemExit("Image publication requires a version tag or manual dispatch.")

    # Fixed commands only: neither the tag nor any other event input is executed.
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"],  # noqa: S607
        cwd=root,
        check=False,
    )
    if ancestor.returncode != 0:
        raise SystemExit("Release commit must already be merged into origin/main.")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=root,
        text=True,
    ).strip()
    main_head = subprocess.check_output(
        ["git", "rev-parse", "origin/main"],  # noqa: S607
        cwd=root,
        text=True,
    ).strip()
    current_main = str(head == main_head).lower()
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as file:
            file.write(f"version={version}\ncurrent-main={current_main}\n")
    print(f"Validated version {version} at {head}; updates latest: {current_main}.")


if __name__ == "__main__":
    main()
