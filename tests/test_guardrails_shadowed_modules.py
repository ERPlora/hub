"""No module sits beside a package of its own name: Python imports the package and never reads the file.

Making a long module a package moves it whole into ``<name>/__init__.py``. A ``<name>.py`` left behind, or brought
back by a merge, still reads as the code while nothing runs it.
"""

from collections.abc import Iterable
from pathlib import Path

from allow_list_base import REPO, git


def shadowed_modules(paths: Iterable[str]) -> list[str]:
    """The ``<name>.py`` among ``paths`` that sit beside a ``<name>/__init__.py`` among them."""
    files = set(paths)
    packages = sorted(path.removesuffix("/__init__.py") for path in files if path.endswith("/__init__.py"))
    return [
        f"{package}.py is beside {package}/, which is the one Python imports: delete the file"
        for package in packages
        if f"{package}.py" in files
    ]


def python_files(repo: Path = REPO) -> list[str]:
    """The Python files on disk: the tracked ones and the new ones git does not ignore."""
    listing = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py")
    assert listing.returncode == 0, listing.stderr
    return [path for path in listing.stdout.split("\0") if path and (repo / path).is_file()]


def test_a_module_beside_a_package_of_its_name_is_caught_and_nothing_else_is():
    paths = [
        "base/schemas.py",
        "base/schemas/__init__.py",
        "base/tests/helpers.py",
        "base/tests/helpers/__init__.py",
        "apps/sale/services/__init__.py",
        "apps/sale/services/order.py",
        "apps/sale/models.py",
        # A folder without __init__.py is no package Python prefers to the module.
        "apps/sale/queries.py",
        "apps/sale/queries/order.py",
        "manage.py",
    ]

    assert shadowed_modules(paths) == [
        "base/schemas.py is beside base/schemas/, which is the one Python imports: delete the file",
        "base/tests/helpers.py is beside base/tests/helpers/, which is the one Python imports: delete the file",
    ]


def test_no_module_of_the_hub_sits_beside_a_package_of_its_name():
    paths = python_files()

    assert "base/__init__.py" in paths, "git ls-files listed no package"
    assert shadowed_modules(paths) == []
