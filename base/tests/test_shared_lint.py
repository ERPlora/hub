"""Only ``base/catalog.py`` reaches the SaaS's ``shared`` schema (round 16, PLAN §21; spec §3.3).

It is the single exception to «only ``services.py`` and ``queries.py`` touch the ORM», as
``base/tenancy/migrator.py`` is for the DDL: ``register_apps`` runs for no hub and no user, so it is
no ``@operation``. Everywhere else in the Hub's source (outside ``tests/``), nothing imports
``shared.models`` and nothing names the ``shared`` alias by hand (``using=``, ``.using(``,
``connections[``). ``base/routers.py`` returns the alias, which is a router's job, not a choice.
Static and fast, proven by a made-up offender first.
"""

import ast
from pathlib import Path, PurePosixPath

HUB_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE_ROOTS = ("base", "apps", "config", "shared")
#: The only file that may: the registry of the Hub's modules in the SaaS.
OWNER = PurePosixPath("base/catalog.py")
#: The mirror itself declares the models it is about.
MIRROR = PurePosixPath("shared/models.py")
ALIAS = "shared"
#: A constant that holds the alias counts as naming it.
ALIAS_NAMES = frozenset({"SHARED_ALIAS"})


def _names_the_alias(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return node.value == ALIAS
    if isinstance(node, ast.Name):
        return node.id in ALIAS_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in ALIAS_NAMES
    return False


def shared_touches(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every import of ``shared.models`` and every hand-chosen ``shared`` alias."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {(node.lineno, "import shared.models") for a in node.names if a.name.startswith("shared.models")}
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("shared.models") or (
                node.module == "shared" and any(a.name == "models" for a in node.names)
            ):
                found.add((node.lineno, "import shared.models"))
        elif isinstance(node, ast.keyword) and node.arg == "using" and _names_the_alias(node.value):
            found.add((node.lineno, "using=shared"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "using"
            and any(_names_the_alias(arg) for arg in node.args)
        ):
            found.add((node.lineno, ".using(shared)"))
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, (ast.Name, ast.Attribute))
            and (node.value.id if isinstance(node.value, ast.Name) else node.value.attr) == "connections"
            and _names_the_alias(node.slice)
        ):
            found.add((node.lineno, "connections[shared]"))
    return sorted(found)


def source_files(root: Path) -> list[PurePosixPath]:
    """Every ``.py`` of the Hub's own source (relative to ``root``) outside a ``tests/`` package."""
    files = []
    for top in SOURCE_ROOTS:
        for path in sorted((root / top).rglob("*.py")):
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if "tests" not in relative.parts:
                files.append(relative)
    return files


OFFENDER = """\
import shared.models
from shared import models
from shared.models import App, AppDoc
from django.db import connections, transaction

App.objects.using("shared").all()
App.objects.using(SHARED_ALIAS).count()
with transaction.atomic(using="shared"):
    connections["shared"].cursor()
    connections[routers.SHARED_ALIAS].close()
"""

LOOKALIKES = """\
from base import models
from shared import apps
from django.db import connections

Item.objects.using("default")
connections["default"].cursor()
shared = {"using": "shared"}
transaction.atomic(using=alias)
"""


def test_the_scanner_sees_imports_and_every_way_of_naming_the_alias():
    assert shared_touches(OFFENDER) == [
        (1, "import shared.models"),
        (2, "import shared.models"),
        (3, "import shared.models"),
        (6, ".using(shared)"),
        (7, ".using(shared)"),
        (8, "using=shared"),
        (9, "connections[shared]"),
        (10, "connections[shared]"),
    ]


def test_the_scanner_ignores_other_aliases_and_other_modules_of_shared():
    assert shared_touches(LOOKALIKES) == []


def test_only_base_catalog_reaches_the_shared_schema():
    offenders = [
        f"{path}:{line} {what}"
        for path in source_files(HUB_DIR)
        if path not in (OWNER, MIRROR)
        for line, what in shared_touches((HUB_DIR / path).read_text())
    ]

    assert offenders == [], (
        "Only base/catalog.py reaches the SaaS's shared schema (spec §3.3): register_apps goes "
        f"through it, never an operation nor another module: {offenders}"
    )


def test_base_catalog_is_where_it_happens():
    # Real code, real touches: a scanner that went blind would let the check above pass.
    touches = {what for _, what in shared_touches((HUB_DIR / OWNER).read_text())}
    assert {"import shared.models", "using=shared"} <= touches
