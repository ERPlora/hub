"""The WORKBOOK's «Lo que necesita de otras apps» names exactly what Inventory uses of the other apps.

Every operation of another app the table names is called by Inventory's code (the server through
``live.operations.get``, the screens through ``useLive``, ``useCommand`` or the typed client) and every
model it names is read; the other way round, nothing Inventory calls or reads of another app is missing
from the table. Tests, migrations and the screens' tests are not Inventory's code.
"""

import ast
import re
from pathlib import Path

from django.apps import apps
from live.operations import UnknownOperation, get

APP = Path(apps.get_app_config("inventory").path)
SECTION = "### Lo que necesita de otras apps"
OPERATION = re.compile(r"(?P<app>[a-z][a-z_]*)\.[a-z_]+\.[a-z_]+")
MODEL = re.compile(r"(?P<app>[a-z][a-z_]*)\.[A-Z][A-Za-z]*")
MODELS_MODULE = re.compile(r"apps\.(?P<app>[a-z_]+)\.models")
# A call whose first argument names an operation: useLive('…'), useCommand('…'), client.api.call('…').
SCREEN_CALL = re.compile(r"[\w$]+\(\s*(['\"])(?P<name>[a-z][a-z_]*\.[a-z_]+\.[a-z_]+)\1")


def needs_table(workbook: str) -> list[dict[str, str]]:
    """The rows of the «Lo que necesita de otras apps» table, as ``{header: cell}``."""
    lines = workbook.splitlines()
    rows = []
    for line in lines[lines.index(SECTION) + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    header, _rule, *body = rows
    return [dict(zip(header, row, strict=True)) for row in body]


def cited() -> set[str]:
    """Every name between backticks in the table's «Servicio» column."""
    rows = needs_table((APP / "WORKBOOK.md").read_text(encoding="utf-8"))
    return {name for row in rows for name in re.findall(r"`([^`]+)`", row["Servicio"])}


def sources(*suffixes: str) -> list[Path]:
    """Inventory's own code with one of ``suffixes``: no tests, no migrations, no screens' tests."""
    found = []
    for path in sorted(APP.rglob("*")):
        parts = path.relative_to(APP).parts
        if path.suffix not in suffixes or parts[0] in {"tests", "migrations"} or "__tests__" in parts:
            continue
        if path.name.endswith(".test.ts") or "node_modules" in parts:
            continue
        found.append(path)
    return found


def is_operation(name: str) -> bool:
    try:
        get(name)
    except UnknownOperation:
        return False
    return True


def server_uses() -> set[str]:
    """The operations the server calls by name (``get("<op>")``) and the models of apps it reads."""
    used = set()
    for path in sources(".py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                used.add(node.args[0].value)
            elif isinstance(node, ast.ImportFrom) and (found := MODELS_MODULE.fullmatch(node.module or "")):
                used.update(f"{found['app']}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and MODEL.fullmatch(node.value):
                used.add(node.value)  # a foreign key's "<app>.<Model>"
    return used


def screen_uses() -> set[str]:
    """The operations the screens call: a call whose first argument is an operation's name."""
    return {
        found["name"]
        for path in sources(".ts", ".vue")
        for found in SCREEN_CALL.finditer(path.read_text(encoding="utf-8"))
        if is_operation(found["name"])
    }


def of_other_apps(names: set[str]) -> set[str]:
    return {
        name
        for name in names
        if (found := OPERATION.fullmatch(name) or MODEL.fullmatch(name)) and found["app"] != "inventory"
    }


def test_every_name_in_the_table_is_an_operation_or_a_model_of_another_app():
    names = cited()
    assert names, "the table names nothing: the test reads the wrong section"
    assert sorted(name for name in names if name not in of_other_apps(names)) == []
    assert sorted(name for name in names if OPERATION.fullmatch(name) and not is_operation(name)) == []


def test_the_table_names_only_what_inventory_calls_or_reads():
    used = of_other_apps(server_uses() | screen_uses())
    assert sorted(cited() - used) == []


def test_the_table_names_everything_inventory_calls_or_reads_of_other_apps():
    used = of_other_apps(server_uses() | screen_uses())
    assert sorted(used - cited()) == []
