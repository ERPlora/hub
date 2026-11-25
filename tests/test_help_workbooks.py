"""Every app whose help is ready publishes only what a customer reads, and all of it, in every language.

For each module that declares ``help`` and each language of the deployment, the help ``base.help.get`` serves: every
entry of the module's menu has its ``###`` under the screens heading, once, and every ``###`` there is one of its tabs;
what it is for (what the first section says before its first ``###``, the only part of it that is published) is not
empty and has at most ``PURPOSE_MAX`` characters; every screen has a summary (what goes before its first ``####``, the
only part of it that is published) of at most ``SUMMARY_MAX`` characters; what is published (what it is for, each
screen's summary, and each flow's title, steps and what happens if it fails) holds no code (backticks), no issue
reference, no size in pixels, no flow id (also a short one, «F09»), no placeholder of a message («{n}», «<total>»), no
Markdown the window's reader does not read («***», a backslash escape), no operation or event name and no quoted title
of a part of the WORKBOOK the window does not show («Pantallas»), while the detail under a ``###`` of the first section
or a ``####`` of a screen may hold any of them; every published flow has its steps; and no flow that reads as done on a
tab is left out, also when its screen names the tab with an arrow or «y» instead of a comma. A translation
publishes the same tabs and flows as its source, each with its steps and what happens if it fails when the source has
them, so a word of the vocabulary that is missing or wrong in it cannot empty the help in that language. The platform (base)
publishes its screens alone: each one it declares has its ``###``, once, under the same rules of text, and a ``###`` that
is no screen (the bell, the side menu) stays in the file. The made-up WORKBOOKs below, clean and then broken once per
rule, show the check catching what it guards.
"""

import itertools
import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.meta import all_live_app_configs

from base import workbook_help
from base.catalog.workbooks import user_part
from base.queries import app_help
from base.tests.help_workbooks import EN, EN_TABS, EN_WORDS, ES, ES_TABS, ES_WORDS, PLATFORM_ES

FORBIDDEN = {
    "code": re.compile(r"`"),
    "an issue reference": re.compile(r"\w+#\d+"),
    "a size in pixels": re.compile(r"\d+ ?px\b"),
    "a flow id": re.compile(r"[A-Z_]+-F\d+|\bF\d{2,}\b"),
    "a placeholder": re.compile(r"\{[^{}]*\}|<\w[^<>\n]*>"),
    # The window's reader is not CommonMark: it has no bold italics and no backslash escapes, so either shows broken.
    "Markdown the window does not read": re.compile(r"\*\*\*|\\[!-/:-@\[-`{-~]"),
}
#: What a flow's screen may join places with that the help does not read as a comma: an arrow, whose place after it is
#: inside the one before it, and a joining word.
ARROW = re.compile(r"\s*(?:→|->|›)[^,;(]*")
JOINING_WORD = re.compile(r"\s+(?:y|e|o|u|and|or)\s+")
#: The title of a section (``##``) or a part of one (``###``) of the WORKBOOK, and that of a flow.
HEADING = re.compile(r"^#{2,3} +(.+?) *$", re.MULTILINE)
FLOW_HEADING = re.compile(r"^[A-Z][A-Z0-9_]*-F\d+\s")
QUOTES = ("«{}»", '"{}"', "“{}”")
#: ``<app>.<entity>.<action>`` (or ``<fact>``): an operation's or an event's name, when its first part is an app.
DOTTED = re.compile(r"(?<![\w.])([a-z][a-z0-9_]*)\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(?!\w|\.\w)")
#: A screen's summary is two or three sentences, and a short list (a colour legend) where the screen has one.
SUMMARY_MAX = 900
#: What a module is for is two or three sentences, the first thing the window shows.
PURPOSE_MAX = 500
LANGUAGES = [code for code, _name in settings.LANGUAGES]
READY = app_help.ready_apps()
MODULES = [label for label in READY if apps.get_app_config(label).kind == "app"]
PLATFORM = apps.get_app_config("base")


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


def purpose_problems(read: workbook_help.Help) -> list[str]:
    """What it is for, the only text of the first section that is published, when it is empty or longer than
    ``PURPOSE_MAX``."""
    if not read.purpose.strip():
        return ["what it is for is empty before its first ###"]
    if len(read.purpose) > PURPOSE_MAX:
        return [f"what it is for has {len(read.purpose)} characters, more than {PURPOSE_MAX}"]
    return []


def placements(read: workbook_help.Help) -> set[tuple[str, str]]:
    return {(flow.id, tab) for flow in read.flows for tab in flow.screens}


def with_commas(markdown: str, screen_key: str, joining_words: bool, module: str | None) -> str:
    """``markdown`` with each flow's screen cut where a person reads two places: at an arrow (what follows it is left
    out, or, with ``module``, the module's own name before it) and, with ``joining_words``, at a joining word, both
    written as the comma the help reads."""
    own_name = re.compile(rf"(^|[,;])\s*{re.escape(module)}\s*(?:→|->|›)", re.IGNORECASE) if module else None

    def rewrite(line: re.Match) -> str:
        screen = own_name.sub(r"\1", line.group(2)) if own_name else line.group(2)
        screen = JOINING_WORD.sub(", ", screen) if joining_words else screen
        return line.group(1) + ARROW.sub("", screen)

    return re.sub(rf"^({re.escape(screen_key)}:)(.*)$", rewrite, markdown, flags=re.MULTILINE)


def placement_problems(read: workbook_help.Help, markdown: str, tabs, vocabulary: workbook_help.Words, module: str):
    """The tabs a done flow is left out of because its screen names them with an arrow or a joining word: both are cut
    as a comma, keeping and not keeping the joining words (a tab's name may hold one), and reading what goes before an
    arrow both as a tab and as the module's own name («Impresión → Dispositivos»)."""
    readable: set[tuple[str, str]] = set()
    for joining_words, own_name in itertools.product((False, True), (None, module)):
        rewritten = with_commas(markdown, vocabulary.keys["screen"], joining_words, own_name)
        readable |= placements(workbook_help.parse(rewritten, tabs, vocabulary))
    labels = {tab.id: tab.label for tab in tabs}
    return [
        f"{flow} is left out of «{labels[tab]}»: its screen names it with an arrow or a joining word, not a comma"
        for flow, tab in sorted(readable - placements(read))
    ]


def quotes(text: str, title: str) -> bool:
    return any(quote.format(title).casefold() in text.casefold() for quote in QUOTES)


def reference_problems(read: workbook_help.Help, markdown: str, tabs) -> list[str]:
    """What is published that names, in quotes, a section or a part of the WORKBOOK the window does not show: any
    ``##`` or ``###`` but a tab or a flow."""
    labels = {tab.label.casefold() for tab in tabs}
    titles = {title for title in HEADING.findall(markdown) if title.casefold() not in labels}
    titles = {title for title in titles if not FLOW_HEADING.match(title)}
    return [
        f"{where} refers to «{title}», a part of the WORKBOOK the window does not show"
        for where, text in published(read)
        for title in sorted(titles)
        if quotes(text, title)
    ]


def screen_problems(read: workbook_help.Help, tabs, required: set[str]) -> list[str]:
    """The tabs of ``required`` with no section under the screens heading, and those with two."""
    missing = required - {screen.id for screen in read.screens}
    found = [f"the tab «{tab.label}» has no ### under the screens heading" for tab in tabs if tab.id in missing]
    return found + [f"«### {title}» is written twice under the screens heading" for title in read.repeated_screens]


def published_problems(read: workbook_help.Help, markdown: str, tabs) -> list[str]:
    """What breaks the rules in the text that is published."""
    names = {config.label for config in all_live_app_configs()}
    found = purpose_problems(read) + summary_problems(read)
    found += [problem for where, text in published(read) for problem in text_problems(where, text, names)]
    return found + reference_problems(read, markdown, tabs)


def platform_problems(read: workbook_help.Help, markdown: str, tabs) -> list[str]:
    """What breaks the rules in the platform's help, which publishes its screens alone, every one of ``tabs``."""
    return screen_problems(read, tabs, {tab.id for tab in tabs}) + published_problems(read, markdown, tabs)


def problems(markdown: str, tabs, menu: set[str], vocabulary: workbook_help.Words, module: str) -> list[str]:
    """What breaks the rules in the help read from ``markdown`` with ``vocabulary``, for the module named ``module``,
    whose tabs are ``tabs`` and whose menu has the ids ``menu`` (its implicit settings tab is a tab only when the
    WORKBOOK writes it)."""
    read = workbook_help.parse(markdown, tabs, vocabulary)
    found = screen_problems(read, tabs, menu) + published_problems(read, markdown, tabs)
    found += [f"«### {title}» under the screens heading is no tab" for title in read.unknown_screens]
    found += placement_problems(read, markdown, tabs, vocabulary, module)
    found += [f"{flow.id} is published without steps" for flow in read.flows if not flow.steps.strip()]
    return found + [
        f"{draft.id} is done on a tab, but its status «{draft.status}» is not read as done: it is left out"
        for draft in read.unpublished
        if draft.screens and reads_as_done(draft.status, vocabulary.done)
    ]


def shape(read: workbook_help.Help) -> tuple[list[str], list[tuple[str, bool, bool]]]:
    """What a translation publishes as its source does: its tabs, and each flow with or without its steps and failure."""
    return [screen.id for screen in read.screens], [(flow.id, bool(flow.steps), bool(flow.failure)) for flow in read.flows]


def served(config, language: str) -> tuple[str, str, list, workbook_help.Words, str]:
    """The language ``base.help.get`` serves ``config`` in for ``language``, the customer's part it reads there, the
    module's tabs, the words of that language and the module's name in it."""
    language_served, markdown = workbook_help.workbook(Path(config.path), language)
    with translation.override(language_served):
        tabs, vocabulary = app_help.tabs_of(config), workbook_help.words()
        return language_served, markdown, tabs, vocabulary, str(config.verbose_name)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_platform_publishes_only_what_a_customer_reads_of_each_of_its_screens(language):
    _language_served, markdown, tabs, _vocabulary, _module = served(PLATFORM, language)
    assert platform_problems(app_help.help_of(PLATFORM, language)[1], markdown, tabs) == []


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("label", MODULES)
def test_a_ready_module_publishes_only_what_a_customer_reads_and_all_of_it(label, language):
    config = apps.get_app_config(label)
    _language_served, markdown, tabs, vocabulary, module = served(config, language)
    assert problems(markdown, tabs, {nav.id for nav in config.navigation}, vocabulary, module) == []


@pytest.mark.parametrize("language", [code for code in LANGUAGES if code != workbook_help.SOURCE_LANGUAGE])
@pytest.mark.parametrize("label", READY)
def test_the_translation_of_a_ready_app_publishes_what_its_source_does(label, language):
    config = apps.get_app_config(label)
    language_served, translated = app_help.help_of(config, language)
    # Not current: its translation fell behind the source (translate_workbooks --check says how to bring it up to date).
    assert language_served == language
    assert shape(translated) == shape(app_help.help_of(config, workbook_help.SOURCE_LANGUAGE)[1])


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
    return problems(markdown, ES_TABS, MENU, ES_WORDS, "Mesas")


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
        ("se activa.\n", "se activa (F02).\n", "what happens if TABLE-F01 fails has a flow id"),
        ("Una tabla de zonas.", "Sale «{n} zonas».", "the screen «Zonas» has a placeholder"),
        ("Una tabla de mesas.", "Una tabla de mesas que lee table.table.list.", "names 'table.table.list'"),
        ("Pasos:\n1. Pulsa «+».\n", "", "TABLE-F01 is published without steps"),
        ("Estado: hecho\n", "Estado: hecho, también por la API\n", "TABLE-F01 is done on a tab, but its status"),
        ("Tocar una mesa abre su ventana.\n", "", "the screen «Plano de sala» has no summary"),
        ("Una tabla de zonas.", "Z" * (SUMMARY_MAX + 1), f"the summary of «Zonas» has {SUMMARY_MAX + 1} characters"),
        ("Mesas es el plano de la sala.\n", "### Quién la usa\nEl responsable.\n", "what it is for is empty before its"),
        ("Mesas es el plano de la sala.", "M" * (PURPOSE_MAX + 1), f"what it is for has {PURPOSE_MAX + 1} characters"),
        ("Una tabla de zonas.", "Abre «Editando zona — <nombre>».", "the screen «Zonas» has a placeholder: '<nombre>'"),
        ("Pantalla: Zonas\n", "Pantalla: Zonas → Nueva zona\n", "TABLE-F01 is left out of «Zonas»"),
        ("Pantalla: Zonas\n", "Pantalla: Zonas y asistente\n", "TABLE-F01 is left out of «Zonas»"),
        ("Pantalla: Zonas\n", "Pantalla: Zonas, Mesas e Inicio\n", "TABLE-F01 is left out of «Mesas»"),
        ("1. Pulsa «+».", "1. Pulsa «+» (ver «Pantallas»).", "the steps of TABLE-F01 refers to «Pantallas»"),
        ("Una tabla de mesas.", "Una tabla de mesas: *** RESERVADA ***.", "«Mesas» has Markdown the window does not read"),
        ("se activa.\n", "se activa \\(sin nombre\\).\n", "if TABLE-F01 fails has Markdown the window does not read"),
    ],
    ids=[
        "missing-tab",
        "no-tab",
        "twice",
        "backticks",
        "issue",
        "pixels",
        "flow-id",
        "short-flow-id",
        "placeholder",
        "operation",
        "no-steps",
        "dropped",
        "no-summary",
        "long-summary",
        "no-purpose",
        "long-purpose",
        "angle-placeholder",
        "screen-arrow",
        "screen-joined",
        "screen-joined-after-a-tab",
        "reference",
        "triple-asterisk",
        "backslash-escape",
    ],
)
def test_each_rule_catches_the_module_that_breaks_it(before, after, caught):
    assert before in CLEAN
    [problem] = made_up(CLEAN.replace(before, after, 1))
    assert caught in problem


def test_a_summary_of_the_most_characters_allowed_passes():
    assert made_up(CLEAN.replace("Una tabla de zonas.", "Z" * SUMMARY_MAX, 1)) == []


def test_what_it_is_for_of_the_most_characters_allowed_passes():
    assert made_up(CLEAN.replace("Mesas es el plano de la sala.", "M" * PURPOSE_MAX, 1)) == []


def test_what_goes_under_a_subheading_of_what_it_is_for_is_not_checked():
    detail = "### Quién la usa\n\nEl responsable, con `table.zone.create` (hub#12, TABLE-F01), en 8 px.\n" + "R" * 600
    assert made_up(CLEAN.replace("\n## Pantallas\n", f"\n{detail}\n\n## Pantallas\n", 1)) == []


def test_a_dotted_name_that_is_no_app_s_is_no_operation():
    assert made_up(CLEAN.replace("Una tabla de mesas.", "Una tabla de mesas en hubs.erplora.com.", 1)) == []


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Una tabla de mesas.", "Una tabla de mesas con aforo < 4 y > 2."),
        ("1. Pulsa «+».", "1. Pulsa «+» en **Mesas → Zonas** y abre «Zonas» o «Cobrar mesa»."),
        ("1. Pulsa «+».", "1. Pulsa «+»: la zona sale en las pantallas pequeñas."),
        ("Pantalla: Zonas\n", "Pantalla: Zonas; Ventas → Vender; asistente y API\n"),
        ("Pantalla: Zonas\nPasos:\n1. Aún", "Pantalla: Zonas y asistente\nPasos:\n1. Aún"),
    ],
    ids=["comparison", "quoted-tab-and-window", "unquoted-title", "another-module-s-screen", "not-done"],
)
def test_what_reads_like_a_broken_rule_but_is_not_passes(before, after):
    assert before in CLEAN
    assert made_up(CLEAN.replace(before, after, 1)) == []


def test_a_screen_with_the_module_s_own_name_before_the_arrow_is_caught_on_the_tab_after_it():
    assert "Pantalla: Zonas\n" in CLEAN
    found = made_up(CLEAN.replace("Pantalla: Zonas\n", "Pantalla: Mesas → Zonas\n", 1))
    assert any("TABLE-F01 is left out of «Zonas»" in problem for problem in found), found


CLEAN_EN = """\
## What it is for and who it is for

Tables is the floor plan of the room.

## Screens

### Floor plan
Tapping a table opens its window.

### Zones
A table of zones.

### Tables
A table of tables.

## Flows

### TABLE-F01 Create a zone
Status: done
Screen: Zones
Steps:
1. Tap "+": you see "New zone".
If it fails: without a name, the button stays off.
"""


def made_up_en(markdown: str) -> list[str]:
    return problems(markdown, EN_TABS, MENU, EN_WORDS, "Tables")


def test_the_clean_english_module_passes_with_what_you_see_in_quotes():
    assert made_up_en(CLEAN_EN) == []


@pytest.mark.parametrize(
    ("before", "after", "caught"),
    [
        ("Screen: Zones\n", "Screen: Zones and assistant\n", "TABLE-F01 is left out of «Zones»"),
        ('"New zone".', '"New zone" (see "Screens").', "the steps of TABLE-F01 refers to «Screens»"),
    ],
    ids=["screen-joined", "reference"],
)
def test_each_rule_catches_the_english_module_that_breaks_it(before, after, caught):
    assert before in CLEAN_EN
    [problem] = made_up_en(CLEAN_EN.replace(before, after, 1))
    assert caught in problem


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


# ── The made-up platform: its screens alone ────────────────────────────────────────────────────────────────────────

PLATFORM_TABS = (
    workbook_help.Tab("home", "Inicio · Resumen", "/"),
    workbook_help.Tab("files", "Archivos", "/files"),
    workbook_help.Tab("system_logs", "Sistema · Registros", "/system#logs"),
)


def made_up_platform(workbook: str) -> list[str]:
    markdown = user_part(workbook)
    return platform_problems(replace(workbook_help.parse(markdown, PLATFORM_TABS, ES_WORDS), flows=()), markdown, PLATFORM_TABS)


def test_the_clean_platform_passes_with_a_section_that_is_no_screen():
    assert made_up_platform(PLATFORM_ES) == []


@pytest.mark.parametrize(
    ("before", "after", "caught"),
    [
        ("### Archivos\nLos documentos del negocio.\n", "", "the tab «Archivos» has no ###"),
        ("### La campana\n", "### Archivos\nOtros.\n\n### La campana\n", "«### Archivos» is written twice"),
        ("Los documentos", "Los `documentos`", "the screen «Archivos» has code"),
        ("Los documentos del negocio.", "«La campana» avisa.", "«Archivos» refers to «La campana»"),
        ("sin activar nada.", "P" * PURPOSE_MAX, "what it is for has"),
    ],
    ids=["missing", "twice", "code", "reference", "long-purpose"],
)
def test_each_rule_catches_the_platform_that_breaks_it(before, after, caught):
    assert before in PLATFORM_ES
    [problem] = made_up_platform(PLATFORM_ES.replace(before, after, 1))
    assert caught in problem
