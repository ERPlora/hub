"""Which part of the Hub's pytest suite a branch runs in CI, and in how many shards (.github/workflows/test.yml).

    python3 scripts/affected_tests.py --base <ref> --shards <shards of the whole suite>

A branch whose changes all sit inside apps/<id>/ runs the tests of those apps and of the apps that depend on them: the
ones that require them, through every app in between, and the ones whose files import any of those, because tests
import other apps' models and helpers beyond what their app requires. Any other change runs the whole suite, and so does
a branch whose changes cannot be worked out, with a warning that says why. main and pre run the whole suite before they
deploy: they give no base.

It writes the selection job's outputs to stdout: ``paths``, the apps' folders pytest runs (empty for the whole suite),
and ``shards``, the JSON list of the python job's matrix: the whole suite's shards in proportion to the test files
selected, and at least one. What it decided goes to the run's log as an annotation.
"""

import argparse
import ast
import configparser
import json
import math
import re
import subprocess
import sys
from pathlib import Path

APPS = "apps"
IMPORT = re.compile(r"^\s*(?:from|import)\s+apps\.(\w+)", re.MULTILINE)
Graph = dict[str, tuple[set[str], set[str]]]


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


def selection(root: Path, base: str) -> list[str]:
    """The apps' folders whose tests the branch runs, none for the whole suite; it says which and why."""
    if not base:
        say("notice", "no base to compare the branch with: pytest runs the whole suite")
        return []
    try:
        changed = changed_files(root, base)
        graph = app_graph(root)
    except (RuntimeError, OSError, ValueError) as error:
        say("warning", f"what the branch changed since {base} could not be worked out ({error}): "
                       "pytest runs the whole suite")
        return []
    if not changed:
        say("notice", f"nothing changed since {base}: pytest runs the whole suite")
        return []
    outside = [path for path in changed if app_of(path) not in graph]
    if outside:
        say("notice", f"{outside[0]} is not inside an app's folder: pytest runs the whole suite")
        return []
    apps = {app_of(path) for path in changed}
    reached = sorted(affected(apps, graph))
    say("notice", f"only {', '.join(sorted(apps))} changed: pytest runs the tests of {', '.join(reached)}")
    return [f"{APPS}/{name}" for name in reached]


def test_files(root: Path, folders: list[str]) -> int:
    return sum(1 for folder in folders for _ in (root / folder).rglob("test_*.py"))


def shard_count(root: Path, paths: list[str], whole: int) -> int:
    """The whole suite's shards in proportion to the test files the paths hold, and at least one."""
    if not paths:
        return whole
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(root / "pytest.ini")
    every = test_files(root, ini["pytest"]["testpaths"].split())
    return max(1, math.ceil(whole * test_files(root, paths) / every))


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
