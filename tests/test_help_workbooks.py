"""Every module whose help window is ready publishes only what a customer reads, in every language it is served in.

For each module that declares ``help`` and each language of the deployment, the help ``base.help.get`` serves: every
entry of the module's menu has its ``###`` under the screens heading and every ``###`` there is one of its tabs; what is
published (what it is for, each screen, and each flow's title, steps and what happens if it fails) holds no code
(backticks), no issue reference, no size in pixels, no flow id and no operation or event name; and every published flow
has its steps. While no module declares its help, the real cases are an empty set; the made-up WORKBOOK below, clean and
then broken once per rule, shows the check catching what it guards.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.meta import all_live_app_configs

from base import workbook_help
from base.queries import app_help
from base.tests.help_workbooks import ES_TABS, ES_WORDS

FORBIDDEN = {
    "code": re.compile(r"`"),
    "an issue reference": re.compile(r"\w+#\d+"),
    "a size in pixels": re.compile(r"\d+ ?px\b"),
    "a flow id": re.compile(r"[A-Z_]+-F\d+"),
}
#: ``<app>.<entity>.<action>`` (or ``<fact>``): an operation's or an event's name, when its first part is an app.
DOTTED = re.compile(r"(?<![\w.])([a-z][a-z0-9_]*)\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(?!\w|\.\w)")


def published(read: workbook_help.Help) -> Iterator[tuple[str, str]]:
    yield "what it is for", read.purpose
    for screen in read.screens:
        yield f"the screen «{screen.title}»", screen.text
    for flow in read.flows:
        yield f"the title of {flow.id}", flow.title
        yield f"the steps of {flow.id}", flow.steps
        yield f"what happens if {flow.id} fails", flow.failure


def text_problems(where: str, text: str, apps_: set[str]) -> list[str]:
    found = [f"{where} has {what}: {hit.group(0)!r}" for what, rule in FORBIDDEN.items() if (hit := rule.search(text))]
    return found + [f"{where} names {hit.group(0)!r}" for hit in DOTTED.finditer(text) if hit.group(1) in apps_]


def problems(read: workbook_help.Help, tabs, menu: set[str]) -> list[str]:
    """What breaks the rules in ``read``, for a module whose tabs are ``tabs`` and whose menu has the ids ``menu`` (its
    implicit settings tab is a tab only when the WORKBOOK writes it)."""
    documented = {screen.id for screen in read.screens}
    found = [f"the tab «{tab.label}» has no ### under the screens heading" for tab in tabs if tab.id in menu - documented]
    found += [f"«### {title}» under the screens heading is no tab" for title in read.unknown_screens]
    names = {config.label for config in all_live_app_configs()}
    found += [problem for where, text in published(read) for problem in text_problems(where, text, names)]
    return found + [f"{flow.id} is published without steps" for flow in read.flows if not flow.steps.strip()]


@pytest.mark.parametrize("language", [code for code, _name in settings.LANGUAGES])
@pytest.mark.parametrize("label", app_help.ready_apps())
def test_a_ready_module_publishes_only_what_a_customer_reads(label, language):
    config = apps.get_app_config(label)
    served, markdown = workbook_help.workbook(Path(config.path), language)
    with translation.override(served):
        read = workbook_help.parse(markdown, app_help.tabs_of(config), workbook_help.words())
        assert problems(read, app_help.tabs_of(config), {nav.id for nav in config.navigation}) == []


# ── The made-up module: clean, then broken once per rule ───────────────────────────────────────────────────────────

CLEAN = """\
## Para qué sirve y para quién

Mesas es el plano de la sala.

## Pantallas

### Plano de sala
Tocar una mesa abre su ventana.

#### Cobrar mesa
Pide el importe.

### Zonas
Una tabla de zonas.

### Mesas
Una tabla de mesas.

## Flujos

### TABLE-F01 Crear una zona
Estado: hecho
Pantalla: Zonas
Pasos:
1. Pulsa «+».
Sale: la zona (avisa: `table.zone.created`).
Si falla: sin nombre, el botón no se activa.
Implicados: TABLE-F02
"""
MENU = {"floor_plan", "zones", "tables"}


def made_up(markdown: str) -> list[str]:
    return problems(workbook_help.parse(markdown, ES_TABS, ES_WORDS), ES_TABS, MENU)


def test_the_clean_module_passes_with_code_and_ids_where_nothing_is_published():
    assert made_up(CLEAN) == []


@pytest.mark.parametrize(
    ("before", "after", "caught"),
    [
        ("### Mesas\nUna tabla de mesas.\n", "", "the tab «Mesas» has no ###"),
        ("### Mesas\n", "### Pantalla vieja\nNada.\n\n### Mesas\n", "«### Pantalla vieja» under the screens heading is no tab"),
        ("Mesas es el plano", "Mesas es el `plano`", "what it is for has code"),
        ("Una tabla de zonas.", "Una tabla de zonas (hub#888).", "the screen «Zonas» has an issue reference"),
        ("1. Pulsa «+».", "1. Pulsa «+» y arrastra 8 px.", "the steps of TABLE-F01 has a size in pixels"),
        ("se activa.\n", "se activa (TABLE-F02).\n", "what happens if TABLE-F01 fails has a flow id"),
        ("Una tabla de mesas.", "Una tabla de mesas que lee table.table.list.", "names 'table.table.list'"),
        ("Pasos:\n1. Pulsa «+».\n", "", "TABLE-F01 is published without steps"),
    ],
    ids=["missing-tab", "no-tab", "backticks", "issue", "pixels", "flow-id", "operation", "no-steps"],
)
def test_each_rule_catches_the_module_that_breaks_it(before, after, caught):
    assert before in CLEAN
    [problem] = made_up(CLEAN.replace(before, after, 1))
    assert caught in problem


def test_a_dotted_name_that_is_no_app_s_is_no_operation():
    assert made_up(CLEAN.replace("Una tabla de mesas.", "Una tabla de mesas en hubs.erplora.com.", 1)) == []
