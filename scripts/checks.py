"""What ``scripts/checks.sh fast [<since>]`` runs before a change is pushed; .githooks/pre-push runs it on every pushed
commit, in a temporary worktree.

1. The guardrail tests of file size, ruff, the import contracts, cognitive complexity and a test named after each module
   the branch adds, the lists that only shrink included: seconds, without the network or a database.
2. What the change touches: what differs from <since>, uncommitted and untracked files included; by default, where HEAD
   left origin/main, or HEAD's parent on origin/main itself (the point the guardrails' exception lists compare with).
   - ESLint on its TypeScript, JavaScript and Vue files, the typecheck when it touches any, and the Vitest tests related
     to them.
   - pytest on its test files and on each touched module's ``test_<module>.py``, on the Postgres of compose.yaml, in a
     test database of this checkout's own unless TEST_DB_NAME names one. A touched WORKBOOK runs its module's
     ``test_workbook.py`` and the tests that read every WORKBOOK.

Every check runs, and any red one fails the command. The whole suite is the CI's (.github/workflows/test.yml).

A tree without node_modules or packages/ui (the hook's worktree) borrows them from the checkout CHECKS_DEPENDENCIES_FROM
names: its node_modules as a folder of links into that checkout's, and packages/ui at the commit this tree records, out
of that checkout's clone of it.
Python reaches packages/live through the environment's editable install. A frontend check that still lacks one of them
fails naming it, never skipped.
"""

import argparse
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

GUARDRAILS = (
    "tests/test_guardrails_size.py",
    "tests/test_guardrails_lint.py",
    "tests/test_guardrails_ruff.py",
    "tests/test_guardrails_complexity.py",
    "tests/test_guardrails_imports.py",
    "tests/test_guardrails_module_tests.py",
)
WORKBOOK = re.compile(r"WORKBOOK(?:\.[a-z]{2})?\.md")
#: The tests that read every WORKBOOK of the repository, run when any of them changes.
EVERY_WORKBOOK_TESTS = (
    "base/tests/test_workbooks_scheduled_tasks.py",
    "tests/test_help_workbooks.py",
    "tests/test_qa_coverage.py",
    "tests/test_workbook_only_useful.py",
    "tests/test_workbook_translations.py",
)
FRONTEND = (".ts", ".vue", ".js", ".mjs")
UI = Path("packages/ui")
#: What the frontend checks need: the file that shows it is there, and how a person gets it.
NEEDED = {
    "node_modules": (Path("node_modules"), "pnpm install"),
    str(UI): (UI / "package.json", "git submodule update --init"),
}
BASE_REF = "origin/main"
LENDER = "CHECKS_DEPENDENCIES_FROM"


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        sys.exit(f"checks: git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def comparison_point(since: str | None) -> str:
    if since:
        return since
    point = git("merge-base", "HEAD", BASE_REF).strip()
    return point if point != git("rev-parse", "HEAD").strip() else git("rev-parse", "HEAD^").strip()


def touched(point: str) -> list[str]:
    """The files that differ from the point and still exist, untracked ones included."""
    listed = git("diff", "--name-only", "-z", point) + git("ls-files", "--others", "--exclude-standard", "-z")
    return sorted({path for path in listed.split("\0") if Path(path).is_file()})


def named_tests(path: Path) -> list[Path]:
    """Where the module's own tests go, whether they exist yet or not: ``test_<module>.py``, and then
    ``test_<package>_<module>.py`` for a module of a package such as services/, in the tests folder of the nearest
    package that has one. A WORKBOOK in either language is the module's ``test_workbook.py``."""
    stem = "workbook" if WORKBOOK.fullmatch(path.name) else path.stem
    home = next((parent for parent in path.parents if (parent / "tests").is_dir()), Path())
    return list(dict.fromkeys(home / "tests" / name for name in (f"test_{stem}.py", f"test_{path.parent.name}_{stem}.py")))


def tests_of(path: Path) -> list[Path]:
    """The test file itself, or the module's own tests that exist (``named_tests``). A WORKBOOK also runs the tests that
    read every WORKBOOK."""
    if path.name.startswith("test_") and path.suffix == ".py":
        return [path]
    own = [test for test in named_tests(path) if test.is_file()]
    return sorted([*own, *map(Path, EVERY_WORKBOOK_TESTS)] if WORKBOOK.fullmatch(path.name) else own)


def unpack(clone: Path, into: Path) -> None:
    commit = git("rev-parse", f"HEAD:{into}").strip()
    archive = subprocess.run(["git", "-C", str(clone), "archive", commit], capture_output=True, check=False)
    if archive.returncode != 0:
        print(f"checks: {clone} lacks {into} at {commit}: {archive.stderr.decode().strip()}", flush=True)
        return
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(into, filter="data")


def mirror(lender: Path, folder: Path) -> None:
    """``folder`` as a directory of links into the lender's. A link of its own is copied as it is, so that a relative
    one resolves inside this tree: pnpm links the workspace's package as ``@erplora/ui -> ../../packages/ui``, and
    a link to the lender's packages/ui would give the typecheck two copies of its types. Anything else is linked whole.
    """
    folder.mkdir()
    for entry in (lender / folder).iterdir():
        if entry.is_symlink():
            (folder / entry.name).symlink_to(os.readlink(entry))
        elif entry.name.startswith("@") and entry.is_dir():
            mirror(lender, folder / entry.name)
        else:
            (folder / entry.name).symlink_to(entry)


def borrow(lender: Path) -> None:
    if not (UI / "package.json").is_file() and (lender / UI).is_dir():
        unpack(lender / UI, UI)
    modules = Path("node_modules")
    if not modules.exists() and (lender / modules).is_dir():
        mirror(lender, modules)
    if UI.is_dir() and not (UI / modules).exists() and (lender / UI / modules).is_dir():
        (UI / modules).symlink_to(lender / UI / modules)


def run(command: list[str], **env: str) -> bool:
    """Runs one check with its output on the terminal; True when it fails."""
    print(f"checks: {' '.join(command)}", flush=True)
    return subprocess.run(command, env={**os.environ, **env}, check=False).returncode != 0


def frontend_failed(files: list[str]) -> bool:
    if lender := os.environ.get(LENDER):
        borrow(Path(lender))
    missing = [f"{name}: run {fix}" for name, (shown_by, fix) in NEEDED.items() if not shown_by.exists()]
    if missing:
        print(f"checks: ESLint, the typecheck and Vitest need {'; '.join(missing)}", flush=True)
        return True
    steps = (
        ["pnpm", "exec", "eslint", "--no-warn-ignored", *files],
        ["pnpm", "typecheck"],
        ["pnpm", "exec", "vitest", "related", "--run", "--passWithNoTests", *files],
    )
    return any([run(step) for step in steps])


def tests_failed(tests: list[Path]) -> bool:
    checkout = Path(os.environ.get(LENDER) or ".").resolve()
    # Short enough for the settings to keep it whole (config/settings/backends.py), and the same for each checkout.
    database = os.environ.get("TEST_DB_NAME") or f"test_checks_{hashlib.sha256(bytes(checkout)).hexdigest()[:6]}"
    return run([sys.executable, "-m", "pytest", "-q", "--tb=short", *map(str, tests)], TEST_DB_NAME=database)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/checks.sh", description="The checks a change passes before a push.")
    parser.add_argument("mode", choices=["fast"])
    parser.add_argument("since", nargs="?", help=f"the commit to compare with (default: where HEAD left {BASE_REF})")
    args = parser.parse_args(argv)
    files = touched(comparison_point(args.since))
    frontend = [path for path in files if path.endswith(FRONTEND)]
    tests = sorted({test for path in files for test in tests_of(Path(path))})
    failed = run([sys.executable, "-m", "pytest", "-q", "--tb=short", *GUARDRAILS])
    if frontend:
        failed = frontend_failed(frontend) or failed
    if tests:
        failed = tests_failed(tests) or failed
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
