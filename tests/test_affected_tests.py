"""Tests of scripts/affected_tests.py: which part of the pytest suite a branch runs in CI, and in how many shards.

Each test builds a small repository of its own with real git: a platform folder, five apps that require or import one
another, and a branch that changes some of their files. The script runs in it as test.yml's selection job runs it, and
the test reads what it hands to the python job (the test paths and the shards) and what it says in the log.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "affected_tests.py"
WHOLE_SUITE = {"paths": "", "shards": [1, 2, 3]}
#: The apps of every repository: what each one requires and the other apps its tests import.
APPS = {
    "tax": ([], []),
    "sale": (["tax"], []),
    "table": (["sale"], []),
    "website": ([], []),
    "flow": ([], ["sale"]),
}
PLATFORM_TESTS = 6


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=ci", "-c", "user.email=ci@example.com", "-c", "commit.gpgsign=false",
         "-c", "core.hooksPath=/dev/null", "-c", "init.defaultBranch=main", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return done.stdout


def write(repo: Path, path: str, text: str = "") -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def app_config(name: str, requires: list[str]) -> str:
    lines = ["from live.meta import LiveAppConfig", "", "", f"class {name.title()}Config(LiveAppConfig):",
             f'    name = "apps.{name}"', '    kind = "app"']
    if requires:
        lines.append(f"    requires = {requires!r}")
    return "\n".join(lines) + "\n"


@pytest.fixture
def repo(tmp_path):
    """A repository on branch work, which has just left origin/main and changes nothing yet."""
    git(tmp_path, "init", "-q")
    write(tmp_path, "pytest.ini", "[pytest]\ntestpaths = base apps tests\n")
    write(tmp_path, "pyproject.toml", "[project]\nname = 'hub'\n")
    write(tmp_path, "apps/__init__.py")
    write(tmp_path, "base/helpers.py", "HELP = 1\n")
    for number in range(PLATFORM_TESTS):
        write(tmp_path, f"base/tests/test_platform_{number}.py", "def test_it():\n    pass\n")
    for name, (requires, imports) in APPS.items():
        write(tmp_path, f"apps/{name}/apps.py", app_config(name, requires))
        write(tmp_path, f"apps/{name}/models.py")
        body = "".join(f"from apps.{other}.models import *\n" for other in imports)
        write(tmp_path, f"apps/{name}/tests/test_{name}.py", body + "\n\ndef test_it():\n    pass\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "main")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(tmp_path, "switch", "-q", "-c", "work")
    return tmp_path


def commit(repo: Path, *paths: str) -> None:
    for path in paths:
        write(repo, path, f"# changed on the branch: {path}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "work")


def select(repo: Path, base: str = "origin/main") -> tuple[dict, str]:
    """What the script hands to the python job (its outputs, with shards read as JSON) and its log."""
    done = subprocess.run([sys.executable, str(SCRIPT), "--base", base, "--shards", "3"], cwd=repo,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    outputs = dict(line.split("=", 1) for line in done.stdout.splitlines())
    outputs["shards"] = json.loads(outputs["shards"])
    return outputs, done.stderr


def test_a_change_inside_an_app_no_other_depends_on_runs_that_app_alone_in_one_shard(repo):
    commit(repo, "apps/table/services.py")
    outputs, log = select(repo)
    assert outputs == {"paths": "apps/table", "shards": [1]}
    assert "::notice" in log and "table" in log


def test_a_change_to_an_app_runs_the_apps_that_require_it_and_those_whose_files_import_it(repo):
    commit(repo, "apps/sale/models.py")
    assert select(repo)[0] == {"paths": "apps/flow apps/sale apps/table", "shards": [1]}


def test_requires_are_followed_through_every_app_in_between_and_the_shards_grow_with_the_tests_selected(repo):
    commit(repo, "apps/tax/models.py")
    # 4 of the 11 test files: 3 shards x 4/11, rounded up.
    assert select(repo)[0] == {"paths": "apps/flow apps/sale apps/table apps/tax", "shards": [1, 2]}


def test_changes_in_several_apps_run_each_one_with_the_apps_that_depend_on_it(repo):
    commit(repo, "apps/table/services.py", "apps/website/services.py")
    assert select(repo)[0] == {"paths": "apps/table apps/website", "shards": [1]}


@pytest.mark.parametrize(
    "outside",
    ["base/helpers.py", "pyproject.toml", "uv.lock", ".github/workflows/test.yml", "conftest.py", "tests/test_x.py",
     "apps/__init__.py", "apps/conftest.py"],
)
def test_a_change_outside_the_apps_runs_the_whole_suite_and_says_which_file(repo, outside):
    commit(repo, "apps/table/services.py", outside)
    outputs, log = select(repo)
    assert outputs == WHOLE_SUITE
    assert outside in log


def test_a_removed_app_runs_the_whole_suite(repo):
    git(repo, "rm", "-q", "-r", "apps/website")
    git(repo, "commit", "-q", "-m", "work")
    assert select(repo)[0] == WHOLE_SUITE


def test_a_file_moved_from_the_platform_into_an_app_runs_the_whole_suite(repo):
    git(repo, "mv", "base/helpers.py", "apps/table/helpers.py")
    git(repo, "commit", "-q", "-m", "work")
    outputs, log = select(repo)
    assert outputs == WHOLE_SUITE
    assert "base/helpers.py" in log


def test_a_branch_that_changes_no_python_file_inside_an_app_still_runs_that_app_and_its_dependents(repo):
    commit(repo, "apps/sale/WORKBOOK.md", "apps/sale/frontend/pages/SaleList.vue", "apps/sale/locale/es/django.po")
    assert select(repo)[0] == {"paths": "apps/flow apps/sale apps/table", "shards": [1]}


def test_a_branch_that_changes_nothing_runs_the_whole_suite(repo):
    outputs, log = select(repo)
    assert outputs == WHOLE_SUITE
    assert "nothing changed" in log


def test_without_a_base_as_on_main_and_pre_it_runs_the_whole_suite(repo):
    commit(repo, "apps/table/services.py")
    outputs, log = select(repo, base="")
    assert outputs == WHOLE_SUITE
    assert "::notice" in log and "::warning" not in log


def test_when_the_base_cannot_be_found_it_runs_the_whole_suite_and_warns(repo):
    commit(repo, "apps/table/services.py")
    outputs, log = select(repo, base="origin/nowhere")
    assert outputs == WHOLE_SUITE
    assert "::warning" in log and "origin/nowhere" in log


def test_outside_a_git_repository_it_runs_the_whole_suite_and_warns(tmp_path):
    write(tmp_path, "pytest.ini", "[pytest]\ntestpaths = apps\n")
    outputs, log = select(tmp_path)
    assert outputs == WHOLE_SUITE
    assert "::warning" in log


def test_when_an_app_s_requires_cannot_be_read_it_runs_the_whole_suite_and_warns(repo):
    commit(repo, "apps/table/services.py")
    write(repo, "apps/sale/apps.py", "class SaleConfig(:\n")
    outputs, log = select(repo)
    assert outputs == WHOLE_SUITE
    assert "::warning" in log and "apps/sale/apps.py" in log
