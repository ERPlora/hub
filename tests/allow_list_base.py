"""The commit whose exception lists today's are compared with, so that those lists only shrink.

It is where HEAD left origin/main: a branch behind main does not fail for an exception main has dropped since. On
origin/main itself, or behind it, that point is HEAD, so the parent commit stands in for it and the commit that
reaches main is checked too. Without origin/main there is nothing to compare with, and the check fails rather than
passing unseen.
"""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BASE_REF = "origin/main"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)


def comparison_point(repo: Path = REPO) -> str:
    point = git(repo, "merge-base", "HEAD", BASE_REF)
    if point.returncode != 0:
        pytest.fail(
            f"{BASE_REF} is not available here, so the exception lists cannot be compared with it "
            f"({point.stderr.strip()}). Fetch it with `git fetch origin main`; a CI checkout needs the full history "
            "(fetch-depth: 0)."
        )
    if point.stdout.strip() != git(repo, "rev-parse", "HEAD").stdout.strip():
        return point.stdout.strip()
    parent = git(repo, "rev-parse", "--verify", "--quiet", "HEAD^")
    return parent.stdout.strip() if parent.returncode == 0 else point.stdout.strip()


def file_at_base(path: str, repo: Path = REPO) -> str | None:
    """The file's text at the comparison point, or None where it did not exist yet."""
    point = comparison_point(repo)
    if git(repo, "cat-file", "-e", f"{point}:{path}").returncode != 0:
        return None
    shown = git(repo, "show", f"{point}:{path}")
    assert shown.returncode == 0, shown.stderr
    return shown.stdout


def grep_at_base(pattern: str, *pathspecs: str, repo: Path = REPO) -> list[str]:
    """Each match of the extended regular expression in the files at the comparison point."""
    found = git(repo, "grep", "-h", "-o", "-E", pattern, comparison_point(repo), "--", *pathspecs)
    assert found.returncode in (0, 1), found.stderr
    return found.stdout.splitlines()
