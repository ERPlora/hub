"""Tests of scripts/affected_tests.py: which part of the pytest suite a branch runs in CI, and in how many shards.

Each test builds a small repository of its own with real git: a platform folder, five apps that require or import one
another, and a branch that changes some of their files. The script runs in it as test.yml's selection job runs it, and
the test reads what it hands to the python job (the test paths and the shards) and what it says in the log.
"""

import importlib.util
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
A_TEST = "def test_it():\n    pass\n"
#: The Hub's tests that read each kind of file outside the apps only some tests read.
SIZE_TESTS = ["tests/test_guardrails_size.py"]
E2E_TESTS = [
    "tests/test_guardrails_lint.py", "tests/test_guardrails_size.py", "tests/test_no_internal_references.py",
]
WORKBOOK_TESTS = [
    "base/tests/test_api_help.py", "base/tests/test_catalog_app_registry.py", "base/tests/test_catalog_verticals.py",
    "base/tests/test_catalog_workbooks.py", "base/tests/test_platform_screens.py", "base/tests/test_qa_assistant.py",
    "base/tests/test_queries_app_help.py", "base/tests/test_register_apps.py", "base/tests/test_routers.py",
    "base/tests/test_translate_workbooks.py", "base/tests/test_workbooks_scheduled_tasks.py",
    "tests/test_help_videos.py", "tests/test_help_workbooks.py", "tests/test_no_internal_references.py",
    "tests/test_qa_coverage.py", "tests/test_workbook_only_useful.py", "tests/test_workbook_page_quotes.py",
    "tests/test_workbook_translations.py",
]
READERS = sorted({*SIZE_TESTS, *E2E_TESTS, *WORKBOOK_TESTS})


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


def build(repo: Path, extra: dict[str, str]) -> Path:
    """A repository on branch work, which has just left origin/main and changes nothing yet; extra are more files of
    main, by their path."""
    git(repo, "init", "-q")
    write(repo, "pytest.ini", "[pytest]\ntestpaths = base apps tests\n")
    write(repo, "pyproject.toml", "[project]\nname = 'hub'\n")
    write(repo, "apps/__init__.py")
    write(repo, "base/helpers.py", "HELP = 1\n")
    for number in range(PLATFORM_TESTS):
        write(repo, f"base/tests/test_platform_{number}.py", A_TEST)
    for name, (requires, imports) in APPS.items():
        write(repo, f"apps/{name}/apps.py", app_config(name, requires))
        write(repo, f"apps/{name}/models.py")
        body = "".join(f"from apps.{other}.models import *\n" for other in imports)
        write(repo, f"apps/{name}/tests/test_{name}.py", body + "\n\n" + A_TEST)
    for path, text in extra.items():
        write(repo, path, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "main")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "switch", "-q", "-c", "work")
    return repo


@pytest.fixture
def repo(tmp_path):
    return build(tmp_path, {})


@pytest.fixture
def shared(tmp_path):
    """The repository, with the Hub's tests that read the files outside the apps only some tests read, and a test module
    that another one imports, as tests/test_guardrails_module_tests.py imports tests/test_guardrails_size.py."""
    extra = dict.fromkeys(READERS, A_TEST)
    extra["tests/test_listing.py"] = A_TEST
    extra["tests/test_listing_more.py"] = "from test_listing import test_it as listed\n\n\n" + A_TEST
    return build(tmp_path, extra)


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
    ["base/helpers.py", "pyproject.toml", "uv.lock", ".github/workflows/test.yml", "conftest.py", "tests/helpers.py",
     "base/tests/conftest.py", "base/tests/fake_gateway.py", "apps/__init__.py", "apps/conftest.py",
     ".dup-guard-allow", "complexipy-snapshot.json", "qa/journeys/restaurant.md", "base/frontend/locale/es.json",
     "tests/e2e/qa/probes/sale.json", "tests/e2e/qa/scenarios/bar.json", "tests/e2e/README.md",
     "docker/test_image.py"],
)
def test_a_change_outside_the_apps_runs_the_whole_suite_and_says_which_file(shared, outside):
    commit(shared, "apps/table/services.py", outside)
    outputs, log = select(shared)
    assert outputs == WHOLE_SUITE
    assert outside in log and "::warning" not in log


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
    commit(repo, "apps/sale/frontend/routes.ts", "apps/sale/frontend/pages/SaleList.vue",
           "apps/sale/locale/es/django.po")
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


def test_a_change_to_the_size_allow_list_runs_the_size_test_alone(shared):
    commit(shared, ".file-size-allow")
    outputs, log = select(shared)
    assert outputs == {"paths": " ".join(SIZE_TESTS), "shards": [1]}
    assert "::notice" in log and "::warning" not in log


def test_a_change_to_an_e2e_spec_or_helper_runs_only_the_tests_that_read_tests_e2e(shared):
    commit(shared, "tests/e2e/sale-pos.spec.ts", "tests/e2e/helpers.ts")
    assert select(shared)[0] == {"paths": " ".join(E2E_TESTS), "shards": [1]}


def test_a_change_to_base_s_workbook_runs_the_tests_that_read_the_workbooks(shared):
    commit(shared, "base/WORKBOOK.md")
    assert select(shared)[0]["paths"] == " ".join(WORKBOOK_TESTS)


def test_an_app_s_workbook_in_either_language_runs_its_app_its_dependents_and_the_tests_that_read_the_workbooks(shared):
    commit(shared, "apps/sale/WORKBOOK.en.md")
    assert select(shared)[0]["paths"] == " ".join(sorted(["apps/flow", "apps/sale", "apps/table", *WORKBOOK_TESTS]))


def test_a_changed_test_module_outside_the_apps_runs_itself_beside_the_apps_the_branch_changes(shared):
    commit(shared, "base/tests/test_platform_1.py", "apps/table/services.py")
    assert select(shared)[0] == {"paths": "apps/table base/tests/test_platform_1.py", "shards": [1]}


def test_a_test_module_another_file_imports_is_a_shared_helper_and_runs_the_whole_suite(shared):
    commit(shared, "tests/test_listing.py")
    outputs, log = select(shared)
    assert outputs == WHOLE_SUITE
    assert "tests/test_listing.py" in log and "tests/test_listing_more.py" in log


def test_a_removed_test_module_no_file_imports_adds_nothing_to_run(shared):
    git(shared, "rm", "-q", "base/tests/test_platform_2.py")
    commit(shared, "apps/table/services.py")
    assert select(shared)[0] == {"paths": "apps/table", "shards": [1]}


def test_when_a_test_that_reads_a_changed_file_is_missing_it_runs_the_whole_suite_and_warns(repo):
    commit(repo, ".file-size-allow")
    outputs, log = select(repo)
    assert outputs == WHOLE_SUITE
    assert "::warning" in log and SIZE_TESTS[0] in log


def test_every_test_the_script_runs_for_a_file_only_some_tests_read_exists_in_the_hub():
    spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    named = sorted({test for _, tests in module.READ_BY for test in tests})
    assert named == READERS
    assert [test for test in named if not (SCRIPT.parent.parent / test).is_file()] == []
