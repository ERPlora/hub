"""The WORKBOOK's «Lo que necesita de otras apps» names exactly what Inventory uses of the other apps.

Every operation of another app the table names is named by Inventory's code (the server calls it through
``live.operations.get``, the screens through ``useLive``, ``useCommand`` or the typed client; by name or
through a constant) and every model it names is read; the other way round, nothing Inventory calls or reads
of another app is missing from the table. A comment is not code (a commented-out call is no call), and
tests, migrations and the screens' tests are not Inventory's code.
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
# A one-line string of the screens' code, or a comment to skip (``//``, ``/* */``, ``<!-- -->``): a comment
# only starts outside a string, so the ``//`` of a URL stays in its string.
SCREEN_TOKEN = re.compile(r"(['\"`])(?P<text>(?:\\.|(?!\1)[^\\\n])*)\1|/\*.*?\*/|<!--.*?-->|//[^\n]*", re.S)


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
    """The operations the server names in a string (``get("<op>")`` or a constant it calls) and the models of
    apps it reads: imported from their ``models`` or named by a foreign key (``"<app>.<Model>"``)."""
    used = set()
    for path in sources(".py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (found := MODELS_MODULE.fullmatch(node.module or "")):
                used.update(f"{found['app']}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if MODEL.fullmatch(node.value) or is_operation(node.value):
                    used.add(node.value)
    return used


def screen_uses() -> set[str]:
    """The operations the screens name in a string outside a comment: the first argument of ``useLive``,
    ``useCommand`` or ``client.api.call``, or a constant passed to them."""
    return {
        found["text"]
        for path in sources(".ts", ".vue")
        for found in SCREEN_TOKEN.finditer(path.read_text(encoding="utf-8"))
        if found["text"] and is_operation(found["text"])
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
