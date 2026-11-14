"""An app's two doors to the ORM, ``services`` (writes) and ``queries`` (reads), each a file or a package.

``packaged_doors/`` is a made-up Hub tree with one app, ``shop``, whose two doors are packages one level deep. The
rules accept it as it is, and each copy of it with one thing wrong is caught.
"""

import importlib
import shutil
import sys
from pathlib import Path, PurePosixPath

import pytest
from live import operations
from orm_doors import door_packages, is_door, package_problems
from test_guardrails import HUB_DIR, orm_rule_applies, orm_touches, source_files

MADE_UP = Path(__file__).resolve().parent / "packaged_doors"
#: The made-up app's modules that touch the ORM, all of them behind its doors.
SHOP_ORM = ["apps/shop/queries/order.py", "apps/shop/services/order.py", "apps/shop/services/stock.py"]
SERVICES = PurePosixPath("apps/shop/services")
QUERIES = PurePosixPath("apps/shop/queries")
#: What a Hub's tree may hold, and whether each is a door.
PATHS = {
    "base/services.py": True,
    "control/queries.py": True,
    "apps/sale/services.py": True,
    "apps/sale/queries.py": True,
    "apps/sale/services/__init__.py": True,
    "apps/sale/services/order.py": True,
    "apps/sale/queries/order.py": True,
    "base/services/hub.py": True,
    "apps/sale/models.py": False,
    "apps/sale/api.py": False,
    "apps/sale/services/order/lines.py": False,
    "apps/sale/services/order/services.py": False,
    "apps/sale/services/queries.py": False,
    "apps/sale/queries/services.py": False,
    "apps/sale/helpers/services.py": False,
    "base/tenancy/services.py": False,
    "base/tenancy/router.py": False,
    "apps/sale/helpers/order.py": False,
    "apps/services.py": False,
    "services/order.py": False,
}


def test_a_door_is_the_services_or_queries_file_of_an_app_or_a_module_of_its_package_one_level_deep():
    assert {path: is_door(PurePosixPath(path)) for path in PATHS} == PATHS


def orm_offenders(root: Path) -> list[str]:
    """Rule (a) of ``test_guardrails.py`` over the tree at ``root``: the ORM out of the doors."""
    files = [path for path in source_files(root) if orm_rule_applies(path)]
    return [f"{path}:{line} {what}" for path in files for line, what in orm_touches((root / path).read_text())]


def test_the_orm_in_the_modules_of_a_door_package_is_behind_the_doors():
    touching = [str(path) for path in source_files(MADE_UP) if orm_touches((MADE_UP / path).read_text())]

    # Positive control: the scan reads the package's modules, and they do touch the ORM.
    assert touching == SHOP_ORM
    assert orm_offenders(MADE_UP) == []


def test_a_door_package_that_imports_each_of_its_modules_by_name_is_well_formed():
    assert door_packages(MADE_UP) == [QUERIES, SERVICES]
    assert [package_problems(MADE_UP, package) for package in door_packages(MADE_UP)] == [[], []]


@pytest.fixture
def shop(tmp_path) -> Path:
    """A copy of the made-up tree, to break one thing in it."""
    root = tmp_path / "hub"
    shutil.copytree(MADE_UP, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def write(root: Path, path: str, source: str) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(source)


ORM_READ = "from apps.demo.models import Item\n\n\ndef names():\n    return Item.objects.all()\n"


def read_at(path: str) -> list[str]:
    """What rule (a) reports of ``ORM_READ`` written at ``path``."""
    return [f"{path}:5 .all(", f"{path}:5 .objects"]


def test_the_orm_out_of_the_doors_is_still_caught(shop):
    write(shop, "apps/shop/helpers.py", ORM_READ)

    assert orm_offenders(shop) == read_at("apps/shop/helpers.py")


def test_a_module_named_like_a_door_inside_a_door_package_is_no_door(shop):
    write(shop, "apps/shop/services/queries.py", ORM_READ)

    assert orm_offenders(shop) == read_at("apps/shop/services/queries.py")


def test_a_door_package_two_levels_deep_is_caught_and_so_is_its_orm(shop):
    (shop / SERVICES / "stock.py").unlink()
    write(shop, "apps/shop/services/__init__.py", "from . import order\n")
    write(shop, "apps/shop/services/stock/__init__.py", "")
    write(shop, "apps/shop/services/stock/levels.py", ORM_READ)

    assert orm_offenders(shop) == read_at("apps/shop/services/stock/levels.py")
    assert package_problems(shop, SERVICES) == [
        "apps/shop/services/stock: a package inside a door, which is one level deep: make it a module of "
        "apps/shop/services"
    ]


def test_an_import_star_in_a_door_package_is_caught(shop):
    write(shop, "apps/shop/services/__init__.py", "from .order import *\nfrom . import order, stock\n")
    write(shop, "apps/shop/services/stock.py", "from ..schemas import *\n")

    assert package_problems(shop, SERVICES) == [
        "apps/shop/services/__init__.py:1: import *, which hides what each module declares: import the module by name",
        "apps/shop/services/stock.py:1: import *, which hides what each module declares: import the module by name",
    ]


def test_a_module_of_a_door_package_its_init_never_imports_is_caught(shop):
    # ``from .. import stock`` is the app's own ``stock``, and an import in a function waits for a call.
    write(shop, "apps/shop/services/__init__.py", "from . import order\nfrom .. import stock\n\n\ndef later():\n    from . import stock\n")

    assert package_problems(shop, SERVICES) == [
        "apps/shop/services/stock.py is never imported by apps/shop/services/__init__.py, so its operations are not "
        "registered: add `from . import stock` to it"
    ]


def test_a_module_imported_for_one_of_its_names_counts_as_imported(shop):
    write(shop, "apps/shop/queries/__init__.py", "from .order import list_orders\n")

    assert package_problems(shop, QUERIES) == []


def test_a_folder_without_python_in_a_door_package_is_no_package_inside_it(shop):
    write(shop, "apps/shop/services/__pycache__/order.cpython-314.pyc", "")

    assert package_problems(shop, SERVICES) == []


def test_the_door_packages_of_the_platform_are_read_too(shop):
    write(shop, "base/services/__init__.py", "")
    write(shop, "base/services/hub.py", ORM_READ)

    assert door_packages(shop) == [PurePosixPath("base/services"), QUERIES, SERVICES]
    assert orm_offenders(shop) == []
    assert package_problems(shop, PurePosixPath("base/services")) == [
        "base/services/hub.py is never imported by base/services/__init__.py, so its operations are not registered: "
        "add `from . import hub` to it"
    ]


def test_a_door_package_without_its_init_is_caught(shop):
    (shop / QUERIES / "__init__.py").unlink()

    assert package_problems(shop, QUERIES) == [
        "apps/shop/queries has no __init__.py, so nothing imports its modules and their operations are not registered"
    ]


def test_every_door_package_of_the_hub_is_one_level_deep_and_imports_each_of_its_modules_by_name():
    problems = [problem for package in door_packages(HUB_DIR) for problem in package_problems(HUB_DIR, package)]

    assert problems == []


@pytest.fixture
def own_registry(monkeypatch):
    """An empty registry of operations while the test runs, and the made-up app imported afresh each time."""
    monkeypatch.setattr(operations, "registry", {})
    yield operations.registry
    for name in [name for name in sys.modules if name.startswith("packaged_doors")]:
        del sys.modules[name]


def test_live_registers_the_operations_declared_in_the_modules_of_a_door_package(own_registry):
    importlib.import_module("packaged_doors.apps.shop.services")
    importlib.import_module("packaged_doors.apps.shop.queries")

    assert {name: (op.kind, op.fn.__module__) for name, op in own_registry.items()} == {
        "shop.order.create": ("command", "packaged_doors.apps.shop.services.order"),
        "shop.stock.remove": ("command", "packaged_doors.apps.shop.services.stock"),
        "shop.order.list": ("query", "packaged_doors.apps.shop.queries.order"),
    }
