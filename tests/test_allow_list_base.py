"""Where the exception lists of the size and function limits are compared with origin/main."""

import subprocess
from pathlib import Path

import pytest
from allow_list_base import comparison_point, file_at_base, grep_at_base

ALLOW_FILE = ".file-size-allow"


def run_git(repo: Path, *args: str) -> str:
    """Git in a scratch repository, without the machine's hooks or signing."""
    command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
    command += ["-c", "user.email=t@example.com", *args]
    return subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, allow: str | None) -> str:
    if allow is None:
        (repo / ALLOW_FILE).unlink(missing_ok=True)
    else:
        (repo / ALLOW_FILE).write_text(allow, encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "--allow-empty", "-q", "-m", "change")
    return run_git(repo, "rev-parse", "HEAD")


@pytest.fixture
def scratch_repo(tmp_path):
    run_git(tmp_path, "init", "-q", "-b", "work")
    return tmp_path


def test_without_origin_main_the_comparison_fails_instead_of_passing(scratch_repo):
    commit(scratch_repo, "1100 base/x.py hub#1\n")
    with pytest.raises(pytest.fail.Exception, match="origin/main is not available here"):
        file_at_base(ALLOW_FILE, scratch_repo)


def test_a_branch_is_compared_with_where_it_left_origin_main(scratch_repo):
    commit(scratch_repo, "1200 base/x.py hub#1\n1100 base/y.py hub#1\n")
    left_at = commit(scratch_repo, "1200 base/x.py hub#1\n")
    run_git(scratch_repo, "update-ref", "refs/remotes/origin/main", left_at)
    commit(scratch_repo, "1300 base/x.py hub#1\n")
    assert comparison_point(scratch_repo) == left_at
    assert file_at_base(ALLOW_FILE, scratch_repo) == "1200 base/x.py hub#1\n"


def test_on_origin_main_itself_the_list_is_compared_with_the_parent_commit(scratch_repo):
    parent = commit(scratch_repo, "1200 base/x.py hub#1\n")
    head = commit(scratch_repo, "1300 base/x.py hub#1\n")
    run_git(scratch_repo, "update-ref", "refs/remotes/origin/main", head)
    assert comparison_point(scratch_repo) == parent
    assert file_at_base(ALLOW_FILE, scratch_repo) == "1200 base/x.py hub#1\n"


def test_before_the_list_exists_there_is_nothing_to_compare_with(scratch_repo):
    commit(scratch_repo, None)
    head = commit(scratch_repo, "1200 base/x.py hub#1\n")
    run_git(scratch_repo, "update-ref", "refs/remotes/origin/main", head)
    assert file_at_base(ALLOW_FILE, scratch_repo) is None


def test_a_search_at_the_comparison_point_reads_that_commit_only(scratch_repo):
    (scratch_repo / "a.py").write_text("def f():  # noqa: C901\n    pass\n", encoding="utf-8")
    left_at = commit(scratch_repo, None)
    run_git(scratch_repo, "update-ref", "refs/remotes/origin/main", left_at)
    (scratch_repo / "b.py").write_text("def g():  # noqa: C901, PLR0911\n    pass\n", encoding="utf-8")
    commit(scratch_repo, None)
    assert grep_at_base("noqa: [A-Z0-9, ]+", "*.py", repo=scratch_repo) == ["noqa: C901"]
    assert grep_at_base("noqa: PLR0911", "*.py", repo=scratch_repo) == []


def test_a_shallow_clone_fails_instead_of_comparing_the_list_with_itself(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    run_git(source, "init", "-q", "-b", "main")
    commit(source, "1200 base/x.py hub#1\n")
    commit(source, "1300 base/x.py hub#1\n")
    run_git(tmp_path, "clone", "-q", "--depth", "1", f"file://{source}", "shallow")
    with pytest.raises(pytest.fail.Exception, match="shallow"):
        file_at_base(ALLOW_FILE, tmp_path / "shallow")


def test_a_shallow_clone_of_a_branch_says_it_is_shallow(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    run_git(source, "init", "-q", "-b", "main")
    commit(source, "1200 base/x.py hub#1\n")
    commit(source, "1300 base/x.py hub#1\n")
    run_git(source, "checkout", "-q", "-b", "work", "HEAD~1")
    commit(source, "1100 base/x.py hub#1\n")
    run_git(tmp_path, "clone", "-q", "--depth", "1", "--no-single-branch", f"file://{source}", "shallow")
    with pytest.raises(pytest.fail.Exception, match="This clone is shallow"):
        file_at_base(ALLOW_FILE, tmp_path / "shallow")


def test_the_first_commit_of_a_full_history_is_compared_with_itself(scratch_repo):
    root = commit(scratch_repo, "1200 base/x.py hub#1\n")
    run_git(scratch_repo, "update-ref", "refs/remotes/origin/main", root)
    assert comparison_point(scratch_repo) == root
