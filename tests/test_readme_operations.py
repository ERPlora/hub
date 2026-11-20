"""The «Operaciones» row of each app's README counts what the app really has.

The row tells whoever integrates how many queries and actions the app has and how many routes it serves under
``/api/<app>/``. Those figures go stale without anyone noticing whenever an operation is added or removed, so they are
held here against the operation registry and the API schema, for every app, a new one included.
"""

import re
from collections import Counter
from functools import cache
from pathlib import Path

import pytest
from live.operations import registry

from config.api import api

APPS = Path(__file__).resolve().parent.parent / "apps"
ROW = re.compile(r"^\| Operaciones \|(?P<text>.*)\|\s*$", re.MULTILINE)
#: Only the first figure of each kind counts: a row may go on to number, say, the queries open to API keys.
FIGURES = {
    "queries": re.compile(r"(\d+) consultas"),
    "actions": re.compile(r"(\d+) acciones"),
    "routes": re.compile(r"(\d+) (?:rutas|con (?:su )?ruta)\b"),
}


def rows() -> dict[str, str]:
    """The «Operaciones» row of every app's README, by app; empty when the app has no README or the README no row."""
    found = {}
    for app in sorted(path.parent for path in APPS.glob("*/apps.py")):
        readme = app / "README.md"
        match = ROW.search(readme.read_text(encoding="utf-8")) if readme.is_file() else None
        found[app.name] = match["text"] if match else ""
    return found


def stated(text: str) -> dict[str, int]:
    """The figures a row states, by kind."""
    matches = {kind: pattern.search(text) for kind, pattern in FIGURES.items()}
    return {kind: int(match[1]) for kind, match in matches.items() if match}


@cache
def counted() -> dict[str, Counter]:
    """What each app really has: its queries and actions in the registry, its routes in the API schema."""
    found: dict[str, Counter] = {}
    for operation in registry.values():
        kind = {"query": "queries", "command": "actions"}[operation.kind]
        found.setdefault(operation.app_label, Counter())[kind] += 1
    for path, methods in api.get_openapi_schema()["paths"].items():
        if path.startswith("/api/"):
            found.setdefault(path.split("/")[2], Counter())["routes"] += len(methods)
    return found


def test_every_app_readme_states_its_queries_actions_and_routes():
    unreadable = sorted(app for app, text in rows().items() if stated(text).keys() != FIGURES.keys())
    assert unreadable == []


@pytest.mark.parametrize("app", sorted(rows()))
def test_the_operations_row_counts_what_the_app_has(app):
    figures = stated(rows()[app])
    assert figures == {kind: counted().get(app, Counter())[kind] for kind in figures}


@pytest.mark.parametrize(
    ("text", "figures"),
    [
        (
            "11 consultas (`queries.py`) y 8 acciones (`services.py`), todas con `ai=`; 18 rutas en `/api/tax/…` "
            "(sin ruta: `tax.rule.get`); 7 consultas y acciones abiertas a las API keys (`expose_api`)",
            {"queries": 11, "actions": 8, "routes": 18},
        ),
        (
            "17 consultas (`queries.py`) y 13 acciones (`services.py`), todas con `ai=`; 25 con ruta en "
            "`/api/invoice/…`",
            {"queries": 17, "actions": 13, "routes": 25},
        ),
        ("9 consultas y 4 acciones; 11 con su ruta en `/api/website/…`", {"queries": 9, "actions": 4, "routes": 11}),
        ("6 consultas y 13 acciones, todas con `ai=`; rutas en `/api/cart_checkout/…`", {"queries": 6, "actions": 13}),
        ("Lo que la app hace, sin cifras", {}),
    ],
)
def test_a_row_is_read_for_its_first_figure_of_each_kind(text, figures):
    assert stated(text) == figures
