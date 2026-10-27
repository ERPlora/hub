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
            parts, fuzzy, current = {"msgctxt": [], "msgid": [], "msgstr": []}, False, None
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
