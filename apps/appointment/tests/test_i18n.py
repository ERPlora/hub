"""Every visible text of the appointment app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise

from apps.appointment import queries, schemas, services
from apps.appointment.models import (
    Appointment,
    AppointmentService,
    BlockedTime,
    Counter,
    History,
    Recurring,
    RecurringService,
    Settings,
)
from base.tests.po import catalogue_key, po_entries

LOCALE = Path(apps.get_app_config("appointment").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Settings, Counter, Recurring, RecurringService, Appointment, AppointmentService, History, BlockedTime)


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top, alone or as the values of a dict."""
    found = []
    for value in vars(module).values():
        items = value.values() if isinstance(value, dict) else (value,)
        found += [item for item in items if isinstance(item, Promise)]
    return found


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("appointment")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *(counter.label for counter in config.bell),
        *(text for notice in config.notices for text in (*notice.title, *notice.body) if isinstance(text, Promise)),
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
    for choices in (
        Appointment.Status,
        Appointment.Source,
        Recurring.Frequency,
        History.Action,
        BlockedTime.BlockType,
    ):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    """Each text is looked up as the compiled catalogue keys it, context included: a ``pgettext_lazy`` that goes back
    to ``_()``, or whose context has a typo, is missing from the catalogue and Spanish says it in English or in
    another app's words (hub#975)."""
    texts = visible_texts()
    assert len(texts) > 100  # positive control: the collection found the app's texts...
    assert len({key for key in texts if "\x04" in key}) >= 10  # ...and kept the context of its pgettext_lazy ones
    assert texts - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("appointment")
        assert str(config.verbose_name) == "Citas"
        assert [str(nav.label) for nav in config.navigation] == ["Citas"]
        assert [str(label) for label in Appointment.Status.labels] == [
            "Pendiente",
            "Confirmada",
            "En curso",
            "Completada",
            "Cancelada",
            "No-show",
        ]
        assert [str(label) for label in Recurring.Frequency.labels] == [
            "Cada día",
            "Cada semana",
            "Cada dos semanas",
            "Cada mes",
        ]
        assert str(queries.VERDICTS["outside_schedule"]) == "Esa hora está fuera del horario del negocio."
        assert str(services.CANNOT["confirm"]) == "Esta cita ya no se puede confirmar: ya no está pendiente."
        assert str(queries.APPOINTMENT_NOT_FOUND) == "Esa cita no existe en este negocio."


def test_spanish_says_citas_own_words_not_an_earlier_apps():
    """The labels Citas shares in English with an app loaded before it come out in Spanish with its own words, the
    ones its screens and WORKBOOK say (hub#633): a series is «activa» (its «Activa» column), the history says «quién»
    did each change, an appointment or a series is «borrada» (its verb is «borrar») and, being a «cita», «creada» and
    «actualizada»; not Django's «activo», Clientes' «por» or «eliminado el», or the «creado» of the apps before it. A
    block («bloqueo») keeps the masculine; and naming a professional or a service takes no comma before «o», as
    Servicios and Ventas, which say the same English, already show."""
    labels = {
        f"{model.__name__}.{name}": model._meta.get_field(name).verbose_name
        for model, names in (
            (Recurring, ("is_active", "deleted_at", "created_at", "updated_at", "created_by")),
            (Appointment, ("deleted_at", "created_at", "updated_at", "created_by", "updated_by")),
            (History, ("actor",)),
            (BlockedTime, ("created_at", "updated_at", "created_by")),
        )
        for name in names
    }
    with translation.override("es"):
        assert {name: str(label) for name, label in labels.items()} == {
            "Recurring.is_active": "activa",
            "Recurring.deleted_at": "borrada el",
            "Recurring.created_at": "creada el",
            "Recurring.updated_at": "actualizada el",
            "Recurring.created_by": "creada por",
            "Appointment.deleted_at": "borrada el",
            "Appointment.created_at": "creada el",
            "Appointment.updated_at": "actualizada el",
            "Appointment.created_by": "creada por",
            "Appointment.updated_by": "actualizada por",
            "History.actor": "quién",
            "BlockedTime.created_at": "creado el",
            "BlockedTime.updated_at": "actualizado el",
            "BlockedTime.created_by": "creado por",
        }
        assert str(schemas.SAY_WHICH_STAFF) == "Di qué profesional: su id o su nombre."
        assert str(schemas.SAY_WHICH_SERVICE) == "Di qué servicio: su id o su nombre."


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/appointment/appointments/confirm",
        json.dumps({"number": "APT-NOPE"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esa cita no existe en este negocio."
