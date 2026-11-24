"""``scripts/checks.sh fast``: what a change passes before it is pushed (.githooks/pre-push runs it on the pushed commit).

It runs the guardrail tests of the size of each file, ruff, the import contracts and the cognitive complexity, the
lists that only shrink included, in seconds, without the network or a database. Then it checks what the change touches:
ESLint on its TypeScript and Vue files, the typecheck when it touches any, the Vitest tests related to them, and pytest
on its test files and on each touched module's ``tests/test_<module>.py``, on Postgres; a touched WORKBOOK runs the
tests that read the WORKBOOKs. A tree that breaks any of them fails the command, and its output names the file and the
reason.

What the change touches is what differs from the commit the command is given, uncommitted and untracked files included.
Each test here gives it the HEAD of a tree of its own, so that it checks only what the test writes.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
#: The checkout with the node_modules and packages/ui the frontend checks borrow: this one, or the one that lends them
#: to the hook's worktree when these tests run there.
LENDER = Path(os.environ.get("CHECKS_DEPENDENCIES_FROM") or REPO)
COMMAND = "scripts/checks.sh"
HELPERS = ("scripts/checks.py",)
KNOTTY = "".join(
    ["def knotty(a, b, c, d, e):\n"]
    + [f"{'    ' * (depth + 1)}if {name}:\n" for depth, name in enumerate("abcdea")]
    + ["                            return 1\n", "    return 0\n"]
)
BREAKS = {
    "apps/demo/filler.py": "".join(f"# filler {line}\n" for line in range(501)),
    "apps/demo/unused.py": "import os\n",
    # Spelled apart so that this file carries no noqa marker of its own. No other marker names B905, so a branch that
    # removes markers cannot make up for this one.
    "apps/demo/silenced.py": "PAIRS = list(zip([1], [2]))  " + "#" + " noqa: B905\n",
    "apps/demo/knotty.py": KNOTTY,
    "base/crossing.py": "import apps.demo\n\nDEMO = apps.demo\n",
}
REPORTS = {
    "size": "apps/demo/filler.py: 501 lines, over its cap of 500",
    "ruff": "apps/demo/unused.py:1:8: F401",
    "frozen noqa markers": "B905: 1 exceptions, 0 where the branch left origin/main",
    "complexity": "apps/demo/knotty.py::knotty scores 21, over 15",
    "imports": "base.crossing -> apps.demo",
}
PROBE_MODULE = "apps/demo/probe.py"
PROBE_TEST = """from django.db import connection

from apps.demo.probe import ANSWER
from apps.demo.tests.conftest import HUB_DB

pytestmark = HUB_DB


def test_the_answer():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        database = cursor.fetchone()[0]
    assert ANSWER == 42, database
"""
BROKEN_TEST = "def test_broken():\n    assert sum([1]) == 2\n"
PROBE_TS = "apps/demo/frontend/probe.ts"
PROBE_TS_TEST = """import { expect, test } from 'vitest';

import { answer } from './probe';

test('the answer', () => {
  expect(answer).toBe(42);
});
"""
# One edit, three faults no other check sees: four parameters (ESLint's max-params), a string where a number is
# declared (the typecheck), and a value the related Vitest test does not expect.
BROKEN_TS = """export const answer: number = 'forty-two';

export function sum(a: number, b: number, c: number, d: number): number {
  return a + b + c + d;
}
"""


def checks(tree: Path, *args: str, database: bool = False, **env: str) -> subprocess.CompletedProcess[str]:
    """The command as the hook runs it: the suite's own pytest settings and test database do not leak into it, and,
    unless it needs one, no database is up."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTEST_") and key not in {"TEST_DB_NAME", "CHECKS_DEPENDENCIES_FROM"}
    }
    environment.update(UV_PROJECT_ENVIRONMENT=sys.prefix, **env)
    if not database:
        environment.update(DB_HOST="127.0.0.1", DB_PORT="1")
    return subprocess.run(
        ["bash", COMMAND, *args], cwd=tree, env=environment, capture_output=True, text=True, timeout=900, check=False
    )


def commit(tree: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        (tree / path).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", *files], cwd=tree, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--no-verify", "--allow-empty"]
        + ["-m", "probe"],
        cwd=tree,
        check=True,
    )


@pytest.fixture
def head_tree(tmp_path):
    """HEAD checked out on its own, with this checkout's command committed on top, so that what a test adds stays out
    of the suite and the command, told to compare with the tree's HEAD, checks only that: were the command itself
    touched, its own tests would run, and each of them runs the command again."""
    tree = tmp_path / "tree"
    subprocess.run(["git", "worktree", "add", "--quiet", "--detach", str(tree), "HEAD"], cwd=REPO, check=True)
    command = {path: (REPO / path).read_text(encoding="utf-8") for path in (COMMAND, *HELPERS) if (REPO / path).is_file()}
    commit(tree, command)
    yield tree
    subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=REPO, check=True)


def test_fast_passes_on_this_tree(head_tree):
    done = checks(head_tree, "fast", "HEAD")
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-2000:]


def test_fast_fails_naming_the_file_and_the_reason_of_every_check(head_tree):
    for path, text in BREAKS.items():
        (head_tree / path).write_text(text, encoding="utf-8")
    done = checks(head_tree, "fast", "HEAD")
    assert done.returncode == 1, done.stdout[-4000:] + done.stderr[-2000:]
    missing = [check for check, report in REPORTS.items() if report not in done.stdout]
    assert missing == [], done.stdout[-8000:]


def test_fast_runs_the_touched_tests_and_those_of_each_touched_module_on_a_database_of_its_own(head_tree):
    commit(head_tree, {PROBE_MODULE: "ANSWER = 42\n", "apps/demo/tests/test_probe.py": PROBE_TEST})
    (head_tree / PROBE_MODULE).write_text("ANSWER = 41\n", encoding="utf-8")
    (head_tree / "apps/demo/tests/test_broken.py").write_text(BROKEN_TEST, encoding="utf-8")
    # A red guardrail first: every check still runs.
    (head_tree / "apps/demo/unused.py").write_text(BREAKS["apps/demo/unused.py"], encoding="utf-8")
    done = checks(head_tree, "fast", "HEAD", database=True)
    output = done.stdout + done.stderr
    assert done.returncode == 1, output[-6000:]
    assert REPORTS["ruff"] in output, output[-6000:]
    assert "FAILED apps/demo/tests/test_probe.py::test_the_answer" in output, output[-6000:]
    assert "FAILED apps/demo/tests/test_broken.py::test_broken" in output, output[-6000:]
    # The database of the run is its own, never the suite's default nor another checkout's.
    assert "AssertionError: test_checks_" in output, output[-6000:]


needs_lent_frontend = pytest.mark.skipif(
    not (LENDER / "node_modules").is_dir() or not (LENDER / "packages/ui/package.json").is_file(),
    reason="needs this checkout's node_modules and packages/ui (pnpm install, git submodule update --init)",
)


@needs_lent_frontend
def test_fast_runs_eslint_the_typecheck_and_the_related_vitest_tests_of_the_touched_frontend_files(head_tree):
    commit(head_tree, {PROBE_TS: "export const answer = 42;\n", "apps/demo/frontend/probe.test.ts": PROBE_TS_TEST})
    (head_tree / PROBE_TS).write_text(BROKEN_TS, encoding="utf-8")
    (head_tree / "apps/demo/unused.py").write_text(BREAKS["apps/demo/unused.py"], encoding="utf-8")
    done = checks(head_tree, "fast", "HEAD", CHECKS_DEPENDENCIES_FROM=str(LENDER))
    output = done.stdout + done.stderr
    assert done.returncode == 1, output[-6000:]
    reports = {
        "ruff": REPORTS["ruff"],
        "eslint": "max-params",
        "typecheck": f"{PROBE_TS}(1,14): error TS2322",
        "vitest": "FAIL  apps/demo/frontend/probe.test.ts > the answer",
    }
    missing = [check for check, report in reports.items() if report not in output]
    assert missing == [], output[-8000:]


@needs_lent_frontend
def test_a_sound_frontend_change_passes_with_the_borrowed_dependencies(head_tree):
    """The workspace's own package resolves to the tree's packages/ui, never to the lender's: two copies of its types
    would fail the typecheck of files the change never touched."""
    commit(head_tree, {PROBE_TS: "export const answer = 42;\n", "apps/demo/frontend/probe.test.ts": PROBE_TS_TEST})
    (head_tree / PROBE_TS).write_text("export const answer = 6 * 7;\n", encoding="utf-8")
    done = checks(head_tree, "fast", "HEAD", CHECKS_DEPENDENCIES_FROM=str(LENDER))
    output = done.stdout + done.stderr
    assert done.returncode == 0, output[-8000:]
    assert f"checks: pnpm exec vitest related --run --passWithNoTests {PROBE_TS}" in output, output[-4000:]


FIXES = {"node_modules": "pnpm install", "packages/ui": "git submodule update --init"}


@pytest.mark.parametrize("lent, lacking", [((), {"node_modules", "packages/ui"}), (("node_modules",), {"packages/ui"})])
def test_the_frontend_checks_fail_naming_what_the_tree_lacks_and_did_not_borrow(head_tree, tmp_path, lent, lacking):
    checkout = tmp_path / "checkout"
    for folder in lent:
        (checkout / folder).mkdir(parents=True)
    (head_tree / PROBE_TS).write_text("export const answer = 42;\n", encoding="utf-8")
    done = checks(head_tree, "fast", "HEAD", CHECKS_DEPENDENCIES_FROM=str(checkout))
    output = done.stdout + done.stderr
    assert done.returncode == 1, output[-4000:]
    named = {name for name, fix in FIXES.items() if f"{name}: run {fix}" in output}
    assert named == lacking, output[-4000:]


@pytest.mark.parametrize(
    "probe, text",
    [
        ("apps/demo/frontend/Probe.vue", "<template><p>probe</p></template>\n"),
        ("apps/demo/frontend/probe.js", "export const answer = 42;\n"),
        ("apps/demo/frontend/probe.mjs", "export const answer = 42;\n"),
    ],
    ids=["vue", "js", "mjs"],
)
def test_a_touched_vue_or_javascript_file_runs_the_frontend_checks_too(head_tree, probe, text):
    (head_tree / probe).write_text(text, encoding="utf-8")
    done = checks(head_tree, "fast", "HEAD")
    output = done.stdout + done.stderr
    assert done.returncode == 1, output[-4000:]
    assert f"node_modules: run {FIXES['node_modules']}" in output, output[-4000:]


def load_helper():
    spec = importlib.util.spec_from_file_location("checks", REPO / HELPERS[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_by_default_the_change_is_what_differs_from_where_head_left_origin_main(tmp_path, monkeypatch):
    helper = load_helper()
    monkeypatch.chdir(tmp_path)
    for variable in [key for key in os.environ if key.startswith("GIT_")]:
        monkeypatch.delenv(variable)
    subprocess.run(["git", "init", "-q"], check=True)
    commit(tmp_path, {"kept.txt": "kept\n", "gone.txt": "gone\n"})
    left = helper.git("rev-parse", "HEAD").strip()
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", left], check=True)
    commit(tmp_path, {"added.txt": "added\n"})
    (tmp_path / "kept.txt").write_text("2\n", encoding="utf-8")
    (tmp_path / "gone.txt").unlink()
    (tmp_path / "untracked.txt").write_text("1\n", encoding="utf-8")

    assert helper.comparison_point(None) == left
    assert helper.touched(left) == ["added.txt", "kept.txt", "untracked.txt"]

    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)
    assert helper.comparison_point(None) == left, "on origin/main itself, HEAD's parent"

    subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/main"], check=True)
    with pytest.raises(SystemExit, match="origin/main"):
        helper.comparison_point(None)


def test_a_module_of_a_package_runs_the_tests_named_after_it_and_after_its_package(tmp_path, monkeypatch):
    helper = load_helper()
    monkeypatch.chdir(tmp_path)
    for path in ("shop/services/orders.py", "shop/tests/test_orders.py", "shop/tests/test_services_orders.py"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("", encoding="utf-8")

    assert helper.tests_of(Path("shop/services/orders.py")) == [
        Path("shop/tests/test_orders.py"),
        Path("shop/tests/test_services_orders.py"),
    ]


#: The tests that read every WORKBOOK of the repository, whichever one changes.
EVERY_WORKBOOK_TESTS = [
    Path("base/tests/test_workbooks_scheduled_tasks.py"),
    Path("tests/test_help_workbooks.py"),
    Path("tests/test_qa_coverage.py"),
    Path("tests/test_workbook_only_useful.py"),
    Path("tests/test_workbook_translations.py"),
]


@pytest.mark.parametrize("workbook", ["shop/WORKBOOK.md", "shop/WORKBOOK.en.md"])
def test_a_workbook_runs_the_tests_that_read_every_workbook_and_its_module_s_own(tmp_path, monkeypatch, workbook):
    assert [test for test in EVERY_WORKBOOK_TESTS if not (REPO / test).is_file()] == []
    helper = load_helper()
    monkeypatch.chdir(tmp_path)
    for path in (workbook, "shop/tests/test_workbook.py"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("", encoding="utf-8")

    assert helper.tests_of(Path(workbook)) == sorted([Path("shop/tests/test_workbook.py"), *EVERY_WORKBOOK_TESTS])


def test_fast_fails_on_a_change_to_a_workbook_alone_that_its_tests_refuse(head_tree):
    """A step that names another flow by its id: the published help refuses it."""
    workbook = head_tree / "apps/inventory/WORKBOOK.md"
    text = workbook.read_text(encoding="utf-8")
    workbook.write_text(text.replace("\nPasos:\n1. ", "\nPasos:\n1. As in INVENTORY-F14, ", 1), encoding="utf-8")
    done = checks(head_tree, "fast", "HEAD", database=True)
    output = done.stdout + done.stderr
    assert done.returncode == 1, output[-6000:]
    assert "FAILED tests/test_help_workbooks.py::" in output, output[-6000:]
    assert "has a flow id: 'INVENTORY-F14'" in output, output[-6000:]


@pytest.mark.parametrize("args", [(), ("slow",)])
def test_an_unknown_mode_says_which_ones_there_are(args):
    done = checks(REPO, *args)
    assert done.returncode == 2
    assert "fast" in done.stderr
