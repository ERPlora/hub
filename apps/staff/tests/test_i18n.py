"""Every visible text of the staff app has its Spanish translation, compiled and current."""

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
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    missing_from_catalogue,
    model_texts,
    po_entries,
    untranslated,
)

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
    lazies += model_texts(MODELS)
    for choices in (Member.Status, TimeOff.LeaveType, TimeOff.Status):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | schema_titles()


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


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Personal by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=100, with_context=10) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


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
