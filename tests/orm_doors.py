"""Which files of the Hub are the doors to the ORM, and the shape of a door that is a package.

An app (``base``, ``control`` or ``apps/<id>``) reads through its ``queries`` and writes through its ``services``: each
is a file (``services.py``) or a package one level deep (``services/<module>.py``). The package's ``__init__.py``
imports each of its modules by name, never with ``import *``, because importing a module is what registers its
operations: a module nobody imports declares operations nobody can call.
"""

import ast
from pathlib import Path, PurePosixPath

DOOR_FILES = frozenset({"services.py", "queries.py"})
DOOR_PACKAGES = frozenset({"services", "queries"})
#: The platform's apps; every folder of ``apps/`` is a module.
PLATFORM_APPS = ("base", "control")


def is_app(folder: PurePosixPath) -> bool:
    return str(folder) in PLATFORM_APPS or (len(folder.parts) == 2 and folder.parts[0] == "apps")


def is_door(path: PurePosixPath) -> bool:
    """An app's ``services.py`` or ``queries.py``, or a module of its ``services/`` or ``queries/`` package. A module of
    the package named ``services`` or ``queries`` is none: it would pass for an app's own file."""
    folder = path.parent
    if is_app(folder):
        return path.name in DOOR_FILES
    return folder.name in DOOR_PACKAGES and is_app(folder.parent) and path.stem not in DOOR_PACKAGES


def door_packages(root: Path) -> list[PurePosixPath]:
    """The ``services/`` and ``queries/`` folders of every app under ``root``."""
    apps = [PurePosixPath(app) for app in PLATFORM_APPS]
    apps += [PurePosixPath("apps", folder.name) for folder in sorted((root / "apps").iterdir())]
    return [app / door for app in apps for door in sorted(DOOR_PACKAGES) if (root / app / door).is_dir()]


def imported_modules(source: str) -> set[str]:
    """The modules of its own package an ``__init__.py`` imports when it runs: ``from . import a`` and ``from .a import
    x``, at its top level (an import inside a function waits for a call)."""
    found: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            found |= {alias.name for alias in node.names} if node.module is None else {node.module}
    return found


def star_imports(source: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
    ]


def package_problems(root: Path, package: PurePosixPath) -> list[str]:
    """What is wrong with the door package ``package`` of the tree at ``root``: a package inside it, an ``import *``, a
    module its ``__init__.py`` never imports, the door's file left beside it, or no ``__init__.py`` at all."""
    folder = root / package
    init = folder / "__init__.py"
    if not init.is_file():
        return [f"{package} has no __init__.py, so nothing imports its modules and their operations are not registered"]
    modules = sorted(folder.glob("*.py"))
    imported = imported_modules(init.read_text())
    problems = [
        f"{package}.py is still there beside {package}/, which is the one Python loads: delete the file"
        for file in [folder.with_suffix(".py")]
        if file.is_file()
    ]
    problems += [
        f"{package}/{inner.name}: a package inside a door, which is one level deep: make it a module of {package}"
        for inner in sorted(folder.iterdir())
        if any(inner.rglob("*.py"))
    ]
    problems += [
        f"{package}/{module.name}:{line}: import *, which hides what each module declares: import the module by name"
        for module in modules
        for line in star_imports(module.read_text())
    ]
    problems += [
        f"{package}/{module.name} is never imported by {package}/__init__.py, so its operations are not registered: "
        f"add `from . import {module.stem}` to it"
        for module in modules
        if module.name != "__init__.py" and module.stem not in imported
    ]
    return problems
