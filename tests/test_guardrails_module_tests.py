"""Every Python module a branch adds comes with its own test, named after it: ``test_<module>.py``, or
``test_<package>_<module>.py`` for a module of a package such as services/, in the tests folder of the nearest package
that has one. It is the test ``scripts/checks.sh fast`` runs whenever the module changes (``named_tests`` in
scripts/checks.py), so a test of the same name in another app does not count: ``base/tests/test_images.py`` does not
test ``apps/combo/schemas/images.py``.

The branch is compared with where it left origin/main (``allow_list_base``), uncommitted and untracked files included,
so the rule holds however the module was written: in an editor, by a shell redirection or by a script. A file git
pairs with one the branch deletes was moved, not added, and does not count; nor do tests and their helpers, generated
files, or a package's ``__init__.py`` that only imports its modules. One with code of its own is named after its
package. git cannot tell whether the test was written first; it can tell that the pair exists.
"""

import ast
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
from allow_list_base import REPO, comparison_point, git
from test_guardrails_size import is_counted, is_test


def load_checks():
    spec = importlib.util.spec_from_file_location("checks", REPO / "scripts/checks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKS = load_checks()


def listed(done: subprocess.CompletedProcess[str]) -> list[str]:
    assert done.returncode == 0, done.stderr
    return [path for path in done.stdout.split("\0") if path]


def added_files(repo: Path) -> list[str]:
    """The files the branch adds, uncommitted and untracked ones included, but those git sees as renamed."""
    point = comparison_point(repo)
    new = listed(git(repo, "diff", "--name-only", "-z", "-M", "--diff-filter=A", point))
    return sorted({*new, *listed(git(repo, "ls-files", "-z", "--others", "--exclude-standard"))})


def only_imports(source: str, path: str) -> bool:
    tree = ast.parse(source, filename=path)
    body = tree.body[1:] if ast.get_docstring(tree) is not None else tree.body
    return all(isinstance(node, ast.Import | ast.ImportFrom) for node in body)


def is_module(path: str, repo: Path) -> bool:
    if not path.endswith(".py") or not is_counted(path) or is_test(path):
        return False
    return Path(path).name != "__init__.py" or not only_imports((repo / path).read_text(encoding="utf-8"), path)


def needed_tests(path: str, repo: Path) -> list[Path]:
    """Where the module's test goes; a package's ``__init__.py`` stands for its package."""
    module = Path(path)
    if module.name == "__init__.py":
        module = module.parent.with_suffix(".py")
    return [test.relative_to(repo) for test in CHECKS.named_tests(repo / module)]


def untested(repo: Path) -> list[str]:
    """Each module the branch adds without a test named after it, and where that test goes."""
    missing = []
    for path in filter(lambda added: is_module(added, repo), added_files(repo)):
        needed = needed_tests(path, repo)
        if not any((repo / test).is_file() for test in needed):
            missing.append(f"{path} has no test named after it: {' or '.join(map(str, needed))}")
    return missing


def test_every_module_the_branch_adds_has_a_test_named_after_it():
    missing = untested(REPO)
    assert missing == [], (
        "A new module needs its own test, named after it, in its app (the one scripts/checks.sh fast runs whenever the "
        "module changes). Write it first:\n" + "\n".join(missing)
    )


def run(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def write(repo: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text, encoding="utf-8")


def save(repo: Path, files: dict[str, str] | None = None) -> None:
    write(repo, files or {})
    run(repo, "add", "-A")
    run(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--no-verify", "-m", "probe")


OLD = "".join(f"def step_{number}():\n    return {number}\n\n\n" for number in range(8))


@pytest.fixture
def branch(tmp_path, monkeypatch):
    """A repository whose origin/main has an app with its tests folder, a module without a test and base's
    ``test_images.py``; what each test commits sits on a branch on top of it."""
    for variable in [key for key in os.environ if key.startswith("GIT_")]:
        monkeypatch.delenv(variable)
    run(tmp_path, "init", "-q")
    save(tmp_path, {"tests/test_root.py": "", "apps/shop/tests/test_shop.py": "", "apps/shop/old.py": OLD})
    save(tmp_path, {"base/tests/test_images.py": ""})
    run(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tmp_path


UNSEEN = "apps/shop/unseen.py has no test named after it: apps/shop/tests/test_unseen.py or apps/shop/tests/test_shop_unseen.py"


def test_a_module_the_branch_adds_without_its_test_is_named_with_the_test_it_needs(branch):
    save(branch, {"apps/shop/unseen.py": "X = 1\n"})
    assert untested(branch) == [UNSEEN]


@pytest.mark.parametrize("staged", [False, True], ids=["untracked", "staged"])
def test_an_uncommitted_module_counts_too(branch, staged):
    write(branch, {"apps/shop/unseen.py": "X = 1\n"})
    if staged:
        run(branch, "add", "apps/shop/unseen.py")
    assert untested(branch) == [UNSEEN]


def test_on_origin_main_itself_the_commit_that_reached_it_is_checked(branch):
    save(branch, {"apps/shop/unseen.py": "X = 1\n"})
    run(branch, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert untested(branch) == [UNSEEN]


def test_a_test_of_the_same_name_in_another_app_does_not_count(branch):
    save(branch, {"apps/shop/schemas/images.py": "X = 1\n"})
    assert untested(branch) == [
        "apps/shop/schemas/images.py has no test named after it: apps/shop/tests/test_images.py or "
        "apps/shop/tests/test_schemas_images.py"
    ]


def test_a_package_s_init_with_code_of_its_own_is_named_after_its_package(branch):
    save(branch, {"apps/shop/pricing/__init__.py": '"""Prices."""\n\nfrom decimal import Decimal\n\nRATE = Decimal(21)\n'})
    assert untested(branch) == [
        "apps/shop/pricing/__init__.py has no test named after it: apps/shop/tests/test_pricing.py or "
        "apps/shop/tests/test_shop_pricing.py"
    ]


INIT_ONLY_IMPORTS = '"""The shop\'s writes: importing each module registers its operations."""\n\nfrom . import orders\n'


@pytest.mark.parametrize(
    "files",
    [
        {"apps/shop/unseen.py": "X = 1\n", "apps/shop/tests/test_unseen.py": ""},
        {"apps/shop/services/orders.py": "X = 1\n", "apps/shop/tests/test_services_orders.py": ""},
        {"apps/shop/services/__init__.py": INIT_ONLY_IMPORTS, "apps/shop/services/orders.py": "X = 1\n"}
        | {"apps/shop/tests/test_orders.py": ""},
        {"apps/shop/services/__init__.py": "import apps.shop.services.orders\n", "apps/shop/services/orders.py": "X = 1\n"}
        | {"apps/shop/tests/test_orders.py": ""},
        {"apps/shop/pricing/__init__.py": "RATE = 21\n", "apps/shop/tests/test_pricing.py": ""},
        {"apps/shop/old.py": OLD + "STEPS = 8\n"},
        {"apps/shop/tests/helpers.py": "X = 1\n", "apps/shop/tests/conftest.py": "", "tests/e2e/stack.py": "X = 1\n"}
        | {"apps/shop/migrations/0002_more.py": "X = 1\n", "apps/shop/frontend/unseen.ts": "export const x = 1;\n"},
    ],
    ids=["its-test", "package-test", "init-only-imports", "init-plain-import", "init-with-its-test", "changed", "no-modules"],
)
def test_a_module_with_its_test_a_changed_one_and_what_is_no_module_pass(branch, files):
    save(branch, files)
    assert untested(branch) == []


@pytest.mark.parametrize("committed", [True, False], ids=["committed", "staged"])
def test_a_module_moved_whole_is_not_new(branch, committed):
    (branch / "apps/shop/moved").mkdir()
    run(branch, "mv", "apps/shop/old.py", "apps/shop/moved/steps.py")
    if committed:
        save(branch)
    assert untested(branch) == []
