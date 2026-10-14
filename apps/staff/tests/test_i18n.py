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
    config = apps.get_app_config("staff")
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
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [
        msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy
    ]
    assert untranslated == []


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
