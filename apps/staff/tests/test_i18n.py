"""Every visible text of the staff app has its Spanish translation, compiled and current."""

import gettext
import json
import re
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.staff import queries, schemas, services
from apps.staff.models import (
    Member,
    Role,
    Schedule,
    ScheduleDay,
    StaffSettings,
    TimeOff,
)

LOCALE = Path(apps.get_app_config("staff").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Role, Member, Schedule, ScheduleDay, TimeOff, StaffSettings)
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
            # A ``#, fuzzy`` read after an entry's end belongs to the entry this line opens;
            # only an end forgets it.
            parts, fuzzy, current = (
                {"msgctxt": [], "msgid": [], "msgstr": []},
                fuzzy and current is None,
                None,
            )
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
    config = apps.get_app_config("staff")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *(widget.title for widget in config.widgets),
        *module_texts(queries),
        *module_texts(services),
        *module_texts(schemas),
    ]
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        # The primary key comes from live.models.UUIDModel: its name is Django's default.
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
        ]
    for choices in (Member.Status, TimeOff.LeaveType, TimeOff.Status):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles staff's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. A title pydantic makes up from the field is not one."""
    titles = set()
    for op in registry.values():
        if op.app_label == "staff":
            for name, prop in op.input.model_json_schema().get("properties", {}).items():
                title = prop.get("title")
                if title and title != name.title().replace("_", " "):
                    titles.add(title)
    return titles


def untranslated(entries: dict[str, tuple[str, bool]]) -> list[str]:
    """The keys gettext shows in English: no ``msgstr``, or a ``#, fuzzy`` one it skips."""
    return [key for key, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert untranslated(entries) == []


def test_the_reader_sees_a_fuzzy_mark_with_and_without_a_context(tmp_path):
    """gettext skips a ``#, fuzzy`` translation (the screen says the English), so the reader
    has to see the mark above a ``msgid`` and above a ``msgctxt``, with or without other
    comments, and never pass it on (hub#492)."""
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
                "#: apps/staff/services.py:1",
                "#, fuzzy, python-format",
                'msgid "With comments %(name)s"',
                'msgstr "Con comentarios %(name)s"',
                "",
                "#, fuzzy",
                'msgctxt "staff member status"',
                'msgid "Active"',
                'msgstr "Activo"',
                'msgctxt "staff member status"',
                'msgid "Inactive"',
                'msgstr ""',
                '"Inactivo"',
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
        "staff member status\x04Active": ("Activo", True),
        "staff member status\x04Inactive": ("Inactivo", False),
    }


def test_a_fuzzy_mark_in_staffs_own_catalog_is_seen(tmp_path):
    """The catalog staff ships, with ``#, fuzzy`` above its first entry and above its first
    entry with a context: the reader flags exactly those two, so the translation guard above
    fails on them (hub#492)."""
    lines = (LOCALE / "django.po").read_text(encoding="utf-8").splitlines()
    first_msgid = next(
        n for n, line in enumerate(lines) if line.startswith("msgid ") and line != 'msgid ""'
    )
    first_msgctxt = next(n for n, line in enumerate(lines) if line.startswith("msgctxt "))
    for n in sorted((first_msgid, first_msgctxt), reverse=True):
        lines.insert(n, "#, fuzzy")
    marked = tmp_path / "django.po"
    marked.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert [lines[first_msgid + 1], lines[first_msgctxt + 2]] == [
        'msgid "Staff"',
        'msgctxt "staff member status"',
    ]
    fuzzy = [key for key, (_, is_fuzzy) in po_entries(marked).items() if is_fuzzy]
    assert fuzzy == ["Staff", "staff member status\x04Active"]
    assert untranslated(po_entries(marked)) == ["Staff", "staff member status\x04Active"]


def test_every_visible_text_is_in_the_catalog():
    assert (
        len(visible_texts()) > 100
    )  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("staff")
        assert str(config.verbose_name) == "Personal"
        assert [str(nav.label) for nav in config.navigation] == [
            "Personal",
            "Roles",
            "Ausencias",
            "Horarios",
        ]
        assert [str(label) for label in Member.Status.labels] == [
            "Activo",
            "Inactivo",
            "De baja",
            "Dado de baja",
        ]
        assert [str(label) for label in TimeOff.LeaveType.labels] == [
            "Vacaciones",
            "Baja por enfermedad",
            "Asuntos propios",
            "Formación",
            "Otros",
        ]
        assert [str(label) for label in TimeOff.Status.labels] == [
            "Pendiente",
            "Aprobada",
            "Rechazada",
            "Cancelada",
        ]
        assert (
            str(queries.MEMBER_NOT_FOUND)
            == "Ese miembro del personal no existe en este negocio."
        )
        assert str(services.ACTIVE_TIME_OFF) == (
            "Ese miembro tiene ausencias pendientes o aprobadas que aún no han terminado. Resuélvelas primero."
        )
        assert (
            str(services.INVALID_TRANSITION)
            == "Esa solicitud de ausencia no puede pasar a ese estado desde el actual."
        )
        assert str(services.DEFAULT_SCHEDULE_NAME) == "Horario habitual"
        assert (
            str(schemas.END_BEFORE_START)
            == "La fecha de fin no puede ser anterior a la de inicio."
        )
        assert (
            str(schemas.NO_DAYS)
            == "Un horario necesita al menos un día de trabajo con horas."
        )


def test_placeholders_survive_the_translation():
    entries = po_entries(LOCALE / "django.po")
    for msgid, (msgstr, _) in entries.items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(
            re.findall(r"%\(\w+\)s", msgstr)
        ), msgid


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/staff/time_off/approve",
        json.dumps({"id": str(uuid.uuid7())}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"]
        == "Esa solicitud de ausencia no existe en este negocio."
    )
