"""Every visible text of the flow app has its Spanish translation, compiled and current."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.flow import queries, recipes, schemas, services
from apps.flow.models import Draft, Flow, FlowRun, Question, Secret

LOCALE = Path(apps.get_app_config("flow").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Flow, FlowRun, Draft, Secret, Question)
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``key → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped).

    The key is the msgid, or ``context\x04msgid`` for an entry with a ``msgctxt`` (gettext's own key).
    """
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        context = _unescape("".join(parts["msgctxt"]))
        if msgid:
            key = f"{context}\x04{msgid}" if context else msgid
            entries[key] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = (
            line.startswith("msgctxt ")
            or (line.startswith("msgid ") and current != "msgctxt")
            or (line.startswith("#") and current == "msgstr")
        )
        if starts_entry:
            flush()
            # A ``#, fuzzy`` read after an entry's end belongs to the entry this line opens; only an end forgets it.
            parts, fuzzy, current = {"msgctxt": [], "msgid": [], "msgstr": []}, fuzzy and current is None, None
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top (error and validation messages)."""
    return [value for value in vars(module).values() if isinstance(value, Promise)]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("flow")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *module_texts(queries),
        *module_texts(services),
        *module_texts(schemas),
        *module_texts(recipes),
    ]
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    for choices in (Flow.Trigger, FlowRun.Status, Draft.Status, Question.Status):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles flow's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. Only the ones flow wrote: pydantic leaves ``title`` empty otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "flow"
        for field in op.input.model_fields.values()
        if field.title
    }


def untranslated(entries: dict[str, tuple[str, bool]]) -> list[str]:
    """The keys gettext shows in English: no ``msgstr``, or a ``#, fuzzy`` one it skips."""
    return [key for key, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert untranslated(entries) == []


def test_the_reader_sees_a_fuzzy_mark_with_and_without_a_context(tmp_path):
    """gettext skips a ``#, fuzzy`` translation (the screen says the English), so the reader has to see the mark
    above a ``msgid`` and above a ``msgctxt``, with or without other comments, and never pass it on (hub#496)."""
    po = tmp_path / "django.po"
    po.write_text(
        "\n".join(
            [
                "#, fuzzy",
                'msgid ""',
                'msgstr ""',
                '"Content-Type: text/plain; charset=UTF-8\\n"',
                "",
                'msgid "Header follows"',
                'msgstr "Tras la cabecera"',
                "",
                "#, fuzzy",
                'msgid "Plain"',
                'msgstr "Llano"',
                'msgid "Right after a fuzzy one"',
                'msgstr "Justo después"',
                "",
                "#. A note for the translator",
                "#: apps/flow/services.py:1",
                "#, fuzzy, python-format",
                'msgid "With comments %(name)s"',
                'msgstr "Con comentarios %(name)s"',
                "",
                "#, fuzzy",
                'msgctxt "automation"',
                'msgid "on"',
                'msgstr "encendida"',
                'msgctxt "automation"',
                'msgid "off"',
                'msgstr ""',
                '"apagada"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert po_entries(po) == {
        "Header follows": ("Tras la cabecera", False),
        "Plain": ("Llano", True),
        "Right after a fuzzy one": ("Justo después", False),
        "With comments %(name)s": ("Con comentarios %(name)s", True),
        "automation\x04on": ("encendida", True),
        "automation\x04off": ("apagada", False),
    }


def test_a_fuzzy_mark_in_flows_own_catalog_is_seen(tmp_path):
    """The catalog flow ships, with ``#, fuzzy`` above its first entry and above its first entry with a context: the
    reader flags exactly those two, so the translation guard above fails on them (hub#496)."""
    lines = (LOCALE / "django.po").read_text(encoding="utf-8").splitlines()
    first_msgid = next(n for n, line in enumerate(lines) if line.startswith("msgid ") and line != 'msgid ""')
    first_msgctxt = next(n for n, line in enumerate(lines) if line.startswith("msgctxt "))
    for n in sorted((first_msgid, first_msgctxt), reverse=True):
        lines.insert(n, "#, fuzzy")
    marked = tmp_path / "django.po"
    marked.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert [lines[first_msgid + 1], lines[first_msgctxt + 2]] == ['msgid "Automations"', 'msgctxt "automation"']
    fuzzy = [key for key, (_, is_fuzzy) in po_entries(marked).items() if is_fuzzy]
    assert fuzzy == ["Automations", "automation\x04on"]
    assert untranslated(po_entries(marked)) == ["Automations", "automation\x04on"]


def test_every_visible_text_is_in_the_catalog():
    assert len(visible_texts()) > 60  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_the_card_says_each_title_with_flows_own_spanish():
    """A title flow shares with an app installed before it («Permissions» with Django's accounts) is said with that
    app's Spanish, so flow's own entry would be dead text: they have to say the same (hub#323)."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = schema_titles()
    assert {"Permissions", "Starts with", "Actor"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("flow")
        assert str(config.verbose_name) == "Automatizaciones"
        assert [str(nav.label) for nav in config.navigation] == ["Automatizaciones"]
        assert [str(label) for label in Flow.Trigger.labels] == [
            "Pasa algo",
            "Según un horario",
            "Una vez, en una fecha y hora",
            "Solo a mano",
        ]
        assert str(services.UNTITLED) == "Automatización sin nombre"
        assert str(services.DISABLED) == "Esta automatización está en pausa: enciéndela para ejecutarla."
        assert str(queries.FLOW_NOT_FOUND) == "Esa automatización no existe en este negocio."


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(re.findall(r"%\(\w+\)s", msgstr)), msgid
