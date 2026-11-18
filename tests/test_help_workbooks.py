"""Every module whose help window is ready publishes only what a customer reads, and all of it, in every language.

For each module that declares ``help`` and each language of the deployment, the help ``base.help.get`` serves: every
entry of the module's menu has its ``###`` under the screens heading, once, and every ``###`` there is one of its tabs;
every screen has a summary (what goes before its first ``####``, the only part of it that is published) of at most
``SUMMARY_MAX`` characters; what is published (what it is for, each screen's summary, and each flow's title, steps and
what happens if it fails) holds no code (backticks), no issue reference, no size in pixels, no flow id and no operation
or event name, while the detail under a ``####`` may hold any of them; every published flow has
its steps; and no flow that reads as done on a tab is left out. A translation publishes the same tabs and flows as its
source, each with its steps and what happens if it fails when the source has them, so a word of the vocabulary that is
missing or wrong in it cannot empty the help in that language. While no module declares its help, the real cases are
an empty set; the made-up WORKBOOKs below, clean and then broken once per rule, show the check catching what it guards.
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
from base.catalog import user_part
from base.queries import app_help
from base.tests.help_workbooks import EN, EN_TABS, EN_WORDS, ES, ES_TABS, ES_WORDS

FORBIDDEN = {
    "code": re.compile(r"`"),
    "an issue reference": re.compile(r"\w+#\d+"),
    "a size in pixels": re.compile(r"\d+ ?px\b"),
    "a flow id": re.compile(r"[A-Z_]+-F\d+"),
}
#: ``<app>.<entity>.<action>`` (or ``<fact>``): an operation's or an event's name, when its first part is an app.
DOTTED = re.compile(r"(?<![\w.])([a-z][a-z0-9_]*)\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(?!\w|\.\w)")
#: A screen's summary is two or three sentences, and a short list (a colour legend) where the screen has one.
SUMMARY_MAX = 900
LANGUAGES = [code for code, _name in settings.LANGUAGES]
READY = app_help.ready_apps()


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


def reads_as_done(status: str, done: str) -> bool:
    """Whether a person reads ``status`` as done: it starts with the done word, whatever follows."""
    status, done = status.casefold(), done.casefold()
    return status.startswith(done) and not status[len(done) : len(done) + 1].isalnum()


def summary_problems(read: workbook_help.Help) -> list[str]:
    """The screens whose summary, the only text of theirs that is published, is empty or longer than ``SUMMARY_MAX``."""
    found = [
        f"the screen «{screen.title}» has no summary before its first ####"
        for screen in read.screens
        if not screen.text.strip()
    ]
    return found + [
        f"the summary of «{screen.title}» has {len(screen.text)} characters, more than {SUMMARY_MAX}"
        for screen in read.screens
        if len(screen.text) > SUMMARY_MAX
    ]


def problems(read: workbook_help.Help, tabs, menu: set[str], done: str) -> list[str]:
    """What breaks the rules in ``read``, for a module whose tabs are ``tabs``, whose menu has the ids ``menu`` (its
    implicit settings tab is a tab only when the WORKBOOK writes it) and whose done flows say ``done``."""
    documented = {screen.id for screen in read.screens}
    found = [f"the tab «{tab.label}» has no ### under the screens heading" for tab in tabs if tab.id in menu - documented]
    found += [f"«### {title}» under the screens heading is no tab" for title in read.unknown_screens]
    found += [f"«### {title}» is written twice under the screens heading" for title in read.repeated_screens]
    found += summary_problems(read)
    names = {config.label for config in all_live_app_configs()}
    found += [problem for where, text in published(read) for problem in text_problems(where, text, names)]
    found += [f"{flow.id} is published without steps" for flow in read.flows if not flow.steps.strip()]
    return found + [
        f"{draft.id} is done on a tab, but its status «{draft.status}» is not read as done: it is left out"
        for draft in read.unpublished
        if draft.screens and reads_as_done(draft.status, done)
    ]


def shape(read: workbook_help.Help) -> tuple[list[str], list[tuple[str, bool, bool]]]:
    """What a translation publishes as its source does: its tabs, and each flow with or without its steps and failure."""
    return [screen.id for screen in read.screens], [(flow.id, bool(flow.steps), bool(flow.failure)) for flow in read.flows]


def served(config, language: str) -> tuple[str, workbook_help.Help, list]:
    """The language ``base.help.get`` serves ``config`` in for ``language``, what it reads there and the module's tabs."""
    language_served, markdown = workbook_help.workbook(Path(config.path), language)
    with translation.override(language_served):
        tabs = app_help.tabs_of(config)
        return language_served, workbook_help.parse(markdown, tabs, workbook_help.words()), tabs


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("label", READY)
def test_a_ready_module_publishes_only_what_a_customer_reads_and_all_of_it(label, language):
    config = apps.get_app_config(label)
    language_served, read, tabs = served(config, language)
    with translation.override(language_served):
        done = workbook_help.words().done
    assert problems(read, tabs, {nav.id for nav in config.navigation}, done) == []


@pytest.mark.parametrize("language", [code for code in LANGUAGES if code != workbook_help.SOURCE_LANGUAGE])
@pytest.mark.parametrize("label", READY)
def test_a_ready_module_s_translation_publishes_what_its_source_does(label, language):
    config = apps.get_app_config(label)
    language_served, translated, _tabs = served(config, language)
    # Not current: its translation fell behind the source (translate_workbooks --check says how to bring it up to date).
    assert language_served == language
    assert shape(translated) == shape(served(config, workbook_help.SOURCE_LANGUAGE)[1])


# ── The made-up module: clean, then broken once per rule ───────────────────────────────────────────────────────────

CLEAN = """\
## Para qué sirve y para quién

Mesas es el plano de la sala.

## Pantallas

### Plano de sala
Tocar una mesa abre su ventana.

#### Cobrar mesa
Pide el importe con `sale.payment.create` (hub#12, TABLE-F02), en un campo de 8 px.

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

### TABLE-F02 Juntar dos zonas
Estado: no hecho, falta la pantalla
Pantalla: Zonas
Pasos:
1. Aún no se puede.
"""
MENU = {"floor_plan", "zones", "tables"}


def made_up(markdown: str) -> list[str]:
    return problems(workbook_help.parse(markdown, ES_TABS, ES_WORDS), ES_TABS, MENU, ES_WORDS.done)


def test_the_clean_module_passes_with_code_and_ids_where_nothing_is_published():
    assert made_up(CLEAN) == []


@pytest.mark.parametrize(
    ("before", "after", "caught"),
    [
        ("### Mesas\nUna tabla de mesas.\n", "", "the tab «Mesas» has no ###"),
        ("### Mesas\n", "### Pantalla vieja\nNada.\n\n### Mesas\n", "«### Pantalla vieja» under the screens heading is no tab"),
        ("### Mesas\n", "### Zonas\nOtra tabla.\n\n### Mesas\n", "«### Zonas» is written twice under the screens heading"),
        ("Mesas es el plano", "Mesas es el `plano`", "what it is for has code"),
        ("Una tabla de zonas.", "Una tabla de zonas (hub#888).", "the screen «Zonas» has an issue reference"),
        ("1. Pulsa «+».", "1. Pulsa «+» y arrastra 8 px.", "the steps of TABLE-F01 has a size in pixels"),
        ("se activa.\n", "se activa (TABLE-F02).\n", "what happens if TABLE-F01 fails has a flow id"),
        ("Una tabla de mesas.", "Una tabla de mesas que lee table.table.list.", "names 'table.table.list'"),
        ("Pasos:\n1. Pulsa «+».\n", "", "TABLE-F01 is published without steps"),
        ("Estado: hecho\n", "Estado: hecho, también por la API\n", "TABLE-F01 is done on a tab, but its status"),
        ("Tocar una mesa abre su ventana.\n", "", "the screen «Plano de sala» has no summary"),
        ("Una tabla de zonas.", "Z" * (SUMMARY_MAX + 1), f"the summary of «Zonas» has {SUMMARY_MAX + 1} characters"),
    ],
    ids=[
        "missing-tab",
        "no-tab",
        "twice",
        "backticks",
        "issue",
        "pixels",
        "flow-id",
        "operation",
        "no-steps",
        "dropped",
        "no-summary",
        "long-summary",
    ],
)
def test_each_rule_catches_the_module_that_breaks_it(before, after, caught):
    assert before in CLEAN
    [problem] = made_up(CLEAN.replace(before, after, 1))
    assert caught in problem


def test_a_summary_of_the_most_characters_allowed_passes():
    assert made_up(CLEAN.replace("Una tabla de zonas.", "Z" * SUMMARY_MAX, 1)) == []


def test_a_dotted_name_that_is_no_app_s_is_no_operation():
    assert made_up(CLEAN.replace("Una tabla de mesas.", "Una tabla de mesas en hubs.erplora.com.", 1)) == []


# ── A translation, against its source ────────────────────────────────────────────────────────────────────────────

SOURCE = shape(workbook_help.parse(user_part(ES), ES_TABS, ES_WORDS))


def test_a_translation_with_its_own_words_publishes_what_its_source_does():
    assert SOURCE == shape(workbook_help.parse(EN, EN_TABS, EN_WORDS))
    assert SOURCE[1]  # positive control: the source publishes flows, with and without what happens if they fail


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("If it fails: without a name", "If fails: without a name"),
        ("Steps:\n1. In **Tables", "Step:\n1. In **Tables"),
        ("Status: done — on the tablet", "Status: hecho — on the tablet"),
        ("## Screens\n", "## Screen\n"),
    ],
    ids=["failure-key", "steps-key", "done-word", "screens-heading"],
)
def test_a_translation_with_one_word_wrong_publishes_less_and_is_caught(before, after):
    assert before in EN
    assert shape(workbook_help.parse(EN.replace(before, after, 1), EN_TABS, EN_WORDS)) != SOURCE


def test_a_translation_read_with_the_source_s_words_is_caught():
    assert shape(workbook_help.parse(EN, EN_TABS, ES_WORDS)) != SOURCE
