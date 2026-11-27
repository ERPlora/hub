"""Which part of the Hub's pytest suite a branch runs in CI, and in how many shards (.github/workflows/test.yml).

    python3 scripts/affected_tests.py --base <ref> --shards <shards of the whole suite>

A change inside apps/<id>/ runs the tests of that app and of the apps that depend on them: the ones that require it,
through every app in between, and the ones whose files import any of those, because tests import other apps' models and
helpers beyond what their app requires. Outside the apps, a test module runs itself, unless another file imports it as a
helper, and a file only some tests read (READ_BY) runs those tests. Any other change runs the whole suite, and so does a
branch whose changes cannot be worked out, with a warning that says why. main, pre and the merge queue run the whole
suite: they give no base.

It writes the selection job's outputs to stdout: ``paths``, the apps' folders and the test files pytest runs (empty for
the whole suite), and ``shards``, the JSON list of the python job's matrix: the whole suite's shards in proportion to the
test files selected, and at least one. What it decided goes to the run's log as an annotation.
"""

import argparse
import ast
import configparser
import functools
import json
import math
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

APPS = "apps"
IMPORT = re.compile(r"^\s*(?:from|import)\s+apps\.(\w+)", re.MULTILINE)
#: pytest's default names of a test module.
TEST_MODULE = re.compile(r"test_\w*\.py|\w+_test\.py")
#: The files outside the apps' code that only some tests read, by a pattern of their path, with the tests that read them.
READ_BY = (
    (re.compile(r"\.file-size-allow"), ("tests/test_guardrails_size.py",)),
    # pytest collects nothing in tests/e2e: Playwright runs its specs, in the job smoke, and Vitest its unit tests. Its
    # qa/ holds the assistant's probes, which the assistant tests of every app read: a change there runs the whole suite.
    (re.compile(r"tests/e2e/(?!qa/).+\.ts"), (
        "tests/test_guardrails_lint.py", "tests/test_guardrails_size.py", "tests/test_no_internal_references.py",
    )),
    # base's and every app's, in either language.
    (re.compile(r"(?:base|apps/\w+)/WORKBOOK(?:\.[a-z]{2})?\.md"), (
        "base/tests/test_api_help.py", "base/tests/test_catalog_app_registry.py",
        "base/tests/test_catalog_verticals.py", "base/tests/test_catalog_workbooks.py",
        "base/tests/test_platform_screens.py", "base/tests/test_qa_assistant.py",
        "base/tests/test_queries_app_help.py", "base/tests/test_register_apps.py", "base/tests/test_routers.py",
        "base/tests/test_translate_workbooks.py", "base/tests/test_workbooks_scheduled_tasks.py",
        "tests/test_help_videos.py", "tests/test_help_workbooks.py", "tests/test_no_internal_references.py",
        "tests/test_qa_coverage.py", "tests/test_workbook_only_useful.py", "tests/test_workbook_page_quotes.py",
        "tests/test_workbook_translations.py",
    )),
)
Graph = dict[str, tuple[set[str], set[str]]]


class WholeSuite(Exception):
    """A change the selection cannot narrow, with the level of its annotation and why."""

    def __init__(self, level: str, reason: str) -> None:
        super().__init__(reason)
        self.level = level


def say(level: str, message: str) -> None:
    print(f"::{level} title=Tests pytest runs::{message}", file=sys.stderr)


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip() or f'exit {done.returncode}'}")
    return done.stdout


def changed_files(root: Path, base: str) -> list[str]:
    """Every file the branch changed since it left base; a moved file counts at its old path and at its new one."""
    point = git(root, "merge-base", "HEAD", base).strip()
    return [path for path in git(root, "diff", "--name-only", "--no-renames", "-z", point, "HEAD").split("\0") if path]


def requires(source: str, filename: str) -> set[str]:
    """The apps an apps.py lists in its AppConfig's ``requires``: none when it lists none."""
    try:
        for node in ast.walk(ast.parse(source, filename=filename)):
            if isinstance(node, ast.Assign) and [getattr(target, "id", None) for target in node.targets] == ["requires"]:
                return set(ast.literal_eval(node.value))
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"{filename}: {error}") from error
    return set()


def imports(folder: Path) -> set[str]:
    """The other apps that any Python file of the app's folder imports, its tests included."""
    found = {name for path in folder.rglob("*.py") for name in IMPORT.findall(path.read_text(encoding="utf-8"))}
    return found - {folder.name}


def app_graph(root: Path) -> Graph:
    """Each app, by its folder's name, with the apps it requires and the other apps its files import."""
    graph = {}
    for config in sorted((root / APPS).glob("*/apps.py")):
        name = config.parent.name
        graph[name] = (requires(config.read_text(encoding="utf-8"), f"{APPS}/{name}/apps.py"), imports(config.parent))
    return graph


def affected(changed: set[str], graph: Graph) -> set[str]:
    """The changed apps, every app that requires one of them through any chain, and the apps that import any of those.

    An app's own code only imports the apps it requires, so a change reaches another app's code through requires. Tests
    import other apps' models and helpers as well, so the apps whose files import a reached app run too.
    """
    reached = set(changed)
    while more := {app for app, (needs, _) in graph.items() if needs & reached} - reached:
        reached |= more
    return reached | {app for app, (_, used) in graph.items() if used & reached}


def app_of(path: str) -> str | None:
    parts = path.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == APPS else None


def testpaths(root: Path) -> tuple[str, ...]:
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(root / "pytest.ini")
    return tuple(ini["pytest"]["testpaths"].split())


def readers(root: Path, path: str) -> set[str]:
    """The tests that read path, when it is one of the files only some tests read (READ_BY), and none otherwise."""
    tests = {test for pattern, names in READ_BY if pattern.fullmatch(path) for test in names}
    missing = sorted(test for test in tests if not (root / test).is_file())
    if missing:
        raise WholeSuite("warning", f"{missing[0]}, which reads {path}, does not exist")
    return tests


@functools.cache
def python_files(root: Path, roots: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Every Python file of pytest's testpaths, by its path, with its text."""
    return tuple((str(path.relative_to(root)), path.read_text(encoding="utf-8"))
                 for folder in roots for path in sorted((root / folder).rglob("*.py")))


def importer(root: Path, roots: tuple[str, ...], module: str) -> str | None:
    """A Python file of pytest's testpaths whose imports name the test module, by its package's path or by itself."""
    imports = re.compile(rf"^\s*(?:from|import)\s[^\n]*\b{re.escape(Path(module).stem)}\b", re.MULTILINE)
    return next((path for path, text in python_files(root, roots) if path != module and imports.search(text)), None)


def own_tests(root: Path, roots: tuple[str, ...], path: str) -> set[str] | None:
    """A test module outside the apps runs itself (nothing once removed); None when path is not one."""
    if not TEST_MODULE.fullmatch(Path(path).name) or path.split("/")[0] not in set(roots) - {APPS}:
        return None
    if user := importer(root, roots, path):
        raise WholeSuite("notice", f"{path} is a test module that {user} imports, as a helper")
    return {path} if (root / path).is_file() else set()


def narrowed(root: Path, changed: list[str], graph: Graph) -> tuple[set[str], set[str]]:
    """The apps the branch changes and the tests outside them it runs; WholeSuite when a change reaches further."""
    roots, apps, tests = testpaths(root), set(), set()
    for path in changed:
        read = readers(root, path)
        tests |= read
        if (app := app_of(path)) in graph:
            apps.add(app)
        elif (own := own_tests(root, roots, path)) is not None:
            tests |= own
        elif not read:
            raise WholeSuite("notice", f"{path} is not inside an app's folder, a test module or a file only some "
                                       "tests read")
    return apps, tests


def selection(root: Path, base: str) -> list[str]:
    """The apps' folders and the test files the branch runs, none for the whole suite; it says which and why."""
    if not base:
        say("notice", "no base to compare the branch with: pytest runs the whole suite")
        return []
    try:
        changed = changed_files(root, base)
        graph = app_graph(root)
        apps, tests = narrowed(root, changed, graph) if changed else (set(), set())
    except (RuntimeError, OSError, ValueError) as error:
        say("warning", f"what the branch changed since {base} could not be worked out ({error}): "
                       "pytest runs the whole suite")
        return []
    except WholeSuite as whole:
        say(whole.level, f"{whole}: pytest runs the whole suite")
        return []
    paths = sorted({f"{APPS}/{name}" for name in affected(apps, graph)} | tests)
    if not paths:
        say("notice", f"nothing changed since {base} that selects a test: pytest runs the whole suite")
        return []
    say("notice", f"pytest runs only what the branch reaches: {', '.join(paths)}")
    return paths


def test_files(root: Path, paths: Iterable[str]) -> int:
    return sum(1 if (root / path).is_file() else sum(1 for _ in (root / path).rglob("test_*.py")) for path in paths)


def shard_count(root: Path, paths: list[str], whole: int) -> int:
    """The whole suite's shards in proportion to the test files the paths hold, and at least one."""
    if not paths:
        return whole
    return max(1, math.ceil(whole * test_files(root, paths) / test_files(root, testpaths(root))))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="the ref the branch is compared with; empty runs the whole suite")
    parser.add_argument("--shards", type=int, required=True, help="how many shards the whole suite runs in")
    args = parser.parse_args(argv)
    root = Path.cwd()
    paths = selection(root, args.base)
    print(f"paths={' '.join(paths)}")
    print(f"shards={json.dumps(list(range(1, shard_count(root, paths, args.shards) + 1)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
