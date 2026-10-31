"""Every visible text of the attendance app has its Spanish translation, compiled and current, and the
short labels carry a context so another app's catalogue never translates them its own way."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.attendance import queries, schemas, services
from apps.attendance.models import AttendanceSettings, Break, Correction, Record

LOCALE = Path(apps.get_app_config("attendance").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Record, Break, Correction, AttendanceSettings)
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
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("attendance")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *(panel.title for panel in config.widgets),
        *module_texts(queries),
        *module_texts(services),
        *module_texts(schemas),
    ]
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    for choices in (Record.Status, Record.Source):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles attendance's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. Only the ones attendance wrote: pydantic leaves ``title`` empty
    otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "attendance"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy] == []


def test_the_reader_sees_a_fuzzy_mark_with_and_without_a_context(tmp_path):
    """gettext skips a ``#, fuzzy`` translation (the screen says the English), so the reader has to see the mark
    above a ``msgid`` and above a ``msgctxt``, with or without other comments, and never pass it on (hub#491)."""
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
                "#: apps/attendance/services.py:1",
                "#, fuzzy, python-format",
                'msgid "With comments %(name)s"',
                'msgstr "Con comentarios %(name)s"',
                "",
                "#, fuzzy",
                'msgctxt "attendance menu"',
                'msgid "Clock in"',
                'msgstr "Fichar entrada"',
                'msgctxt "attendance menu"',
                'msgid "Clock out"',
                'msgstr ""',
                '"Fichar salida"',
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
        "attendance menu\x04Clock in": ("Fichar entrada", True),
        "attendance menu\x04Clock out": ("Fichar salida", False),
    }


def test_a_fuzzy_mark_in_attendances_own_catalog_is_seen(tmp_path):
    """The catalog attendance ships, with ``#, fuzzy`` above its first entry and above its first entry with a
    context: the reader flags exactly those two, so the translation guard above fails on them (hub#491)."""
    lines = (LOCALE / "django.po").read_text(encoding="utf-8").splitlines()
    first_msgid = next(n for n, line in enumerate(lines) if line.startswith("msgid ") and line != 'msgid ""')
    first_msgctxt = next(n for n, line in enumerate(lines) if line.startswith("msgctxt "))
    for n in sorted((first_msgid, first_msgctxt), reverse=True):
        lines.insert(n, "#, fuzzy")
    marked = tmp_path / "django.po"
    marked.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert [lines[first_msgid + 1], lines[first_msgctxt + 2]] == ['msgid "Time clock"', 'msgctxt "attendance menu"']
    fuzzy = [key for key, (_, is_fuzzy) in po_entries(marked).items() if is_fuzzy]
    assert fuzzy == ["Time clock", "attendance menu\x04Clock in"]


def test_every_visible_text_is_in_the_catalog():
    assert len(visible_texts()) > 60  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(re.findall(r"%\(\w+\)s", msgstr)), msgid


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("attendance")
        assert str(config.verbose_name) == "Control horario"
        assert [str(nav.label) for nav in config.navigation] == ["Fichar", "Registros"]
        assert [str(panel.title) for panel in config.widgets] == ["Fichados ahora"]
        assert [str(label) for label in Record.Status.labels] == ["Abierta", "Cerrada", "Por revisar"]
        assert str(services.ALREADY_IN) == "Ya tienes una jornada abierta: ficha la salida antes de volver a entrar."
        assert str(services.OVERLAP) == "Estas horas se solapan con otra jornada de esta persona."
        assert str(schemas.OUT_BEFORE_IN) == "La salida tiene que ser posterior a la entrada."
        assert str(services.OUTSIDE_RADIUS) % {"distance": 850, "radius": 100} == (
            "Estás a 850 m del lugar de trabajo, fuera de los 100 m permitidos. Acércate para fichar o ficha "
            "en el mostrador."
        )
        assert str(queries.TERMINATED_REASON) == "Jornada cerrada al dar de baja a la persona en Personal."


def test_short_labels_carry_their_context():
    # «Open», «Closed», «Clock in» and «Records» are words other apps translate their own way.
    entries = po_entries(LOCALE / "django.po")
    for key in (
        "working day status\x04Open",
        "working day status\x04Closed",
        "working day status\x04Needs review",
        "attendance menu\x04Clock in",
        "attendance menu\x04Records",
    ):
        assert key in entries, key


def said_in_spanish(key: str) -> str:
    """How the Hub says a catalogue entry in Spanish: every app's catalogue merged, the first one to have it winning."""
    with translation.override("es"):
        if "\x04" in key:
            context, msgid = key.split("\x04", 1)
            return translation.pgettext(context, msgid)
        return translation.gettext(key)


def test_no_other_apps_catalogue_says_a_text_of_attendance_its_own_way():
    """Staff's «working day» is a weekday of a schedule («día de trabajo»), attendance's the legal day («jornada»): an
    entry another catalogue also has, without its own context, was said the other app's way."""
    entries = po_entries(LOCALE / "django.po")
    assert len(entries) > 60  # positive control: the catalogue was read
    shadowed = {key: said_in_spanish(key) for key, (msgstr, _) in entries.items() if said_in_spanish(key) != msgstr}
    assert shadowed == {}


def test_a_working_day_is_a_jornada_in_spanish_and_a_working_day_in_english():
    """What the models call the day, the end of a break and the settings' slot: their admin and every screen or card
    that names a datum by its model (the assistant's card, an automation's fields) say them as attendance does."""
    names = lambda: [  # noqa: E731
        str(Record._meta.verbose_name),
        str(Record._meta.verbose_name_plural),
        str(Break._meta.get_field("record").verbose_name),
        str(Correction._meta.get_field("record").verbose_name),
        str(Break._meta.get_field("ended_at").verbose_name),
        str(AttendanceSettings._meta.get_field("slot").verbose_name),
    ]
    with translation.override("es"):
        assert names() == ["jornada", "jornadas", "jornada", "jornada", "terminó a las", "hueco"]
    with translation.override("en"):
        assert names() == ["working day", "working days", "working day", "working day", "ended at", "slot"]


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.get(
        "/api/attendance/records/detail",
        {"id": "0199c8a0-0000-7000-8000-000000000000"},
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esa jornada no existe en este negocio."
    assert json.loads(response.content)["error"]["code"] == "not_found"
