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
from base.tests.po import po_entries

LOCALE = Path(apps.get_app_config("staff").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Role, Member, Schedule, ScheduleDay, TimeOff, StaffSettings)


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
