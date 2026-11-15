"""The commit whose exception lists today's are compared with, so that those lists only shrink.

It is where HEAD left origin/main: a branch behind main does not fail for an exception main has dropped since. On
origin/main itself, or behind it, that point is HEAD, so the parent commit stands in for it and the commit that
reaches main is checked too. Without origin/main, or in a shallow clone that lacks the commits to compare with, there
is nothing to compare with, and the check fails saying which rather than passing unseen; only a true first commit is
compared with itself.
"""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BASE_REF = "origin/main"
FULL_HISTORY = "Fetch the full history (`git fetch --unshallow origin`; in CI, fetch-depth: 0)."


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)


def is_shallow(repo: Path) -> bool:
    return git(repo, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"


def comparison_point(repo: Path = REPO) -> str:
    point = git(repo, "merge-base", "HEAD", BASE_REF)
    if point.returncode != 0 and is_shallow(repo):
        pytest.fail(
            f"This clone is shallow: HEAD and {BASE_REF} share no commit in it, so the exception lists cannot be "
            f"compared. {FULL_HISTORY}"
        )
    if point.returncode != 0:
        pytest.fail(
            f"{BASE_REF} is not available here, so the exception lists cannot be compared with it "
            f"({point.stderr.strip()}). Fetch it with `git fetch origin main`; a CI checkout needs the full history "
            "(fetch-depth: 0)."
        )
    if point.stdout.strip() != git(repo, "rev-parse", "HEAD").stdout.strip():
        return point.stdout.strip()
    parent = git(repo, "rev-parse", "--verify", "--quiet", "HEAD^")
    if parent.returncode == 0:
        return parent.stdout.strip()
    if is_shallow(repo):
        pytest.fail(
            f"This clone is shallow: HEAD's parent is missing, so the exception lists would be compared with "
            f"themselves. {FULL_HISTORY}"
        )
    return point.stdout.strip()


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
