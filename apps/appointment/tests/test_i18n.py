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
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    untranslated,
)

LOCALE = Path(apps.get_app_config("appointment").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Settings, Counter, Recurring, RecurringService, Appointment, AppointmentService, History, BlockedTime)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas, which name a datum on the assistant's card (hub#635)."""
    config = apps.get_app_config("appointment")
    lazies = [
        *config_texts(config),
        *(counter.label for counter in config.bell),
        *(text for notice in config.notices for text in (*notice.title, *notice.body) if isinstance(text, Promise)),
        *module_texts(queries, services, schemas),
    ]
    lazies += model_texts(MODELS)
    for choices in (
        Appointment.Status,
        Appointment.Source,
        Recurring.Frequency,
        History.Action,
        BlockedTime.BlockType,
    ):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("appointment")


def own_catalogue() -> gettext.GNUTranslations:
    """Citas's own compiled Spanish catalogue, read alone: not merged with the other apps' ones."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        return gettext.GNUTranslations(compiled)


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Citas by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=130, with_context=11) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_citas_own_spanish():
    """The assistant's card names a datum by the title its schema gives it, said through every app's catalogue: one an
    app installed before Citas also writes, with other Spanish, would win and leave Citas's entry dead (hub#637)."""
    own = own_catalogue()
    titles = operation_titles("appointment")
    assert {"Book even if it overlaps", "Duplicate customer"} <= titles  # positive control: Citas's titles are read
    # Each title has Spanish of its own: with its entry gone, both sides below would say the English and agree.
    assert sorted(title for title in titles if own.gettext(title) == title) == []
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {title: own.gettext(title) for title in titles}


def test_the_card_says_each_title_with_the_spanish_of_the_workbook():
    """The names the WORKBOOK gives the data of the assistant's card (an appointment is «Cita»; the data no model of
    Citas names, hub#637), with its own words: the one who asks is «la clienta», as its screens and messages say."""
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in operation_titles("appointment")} == {
            "Appointment": "Cita",
            "Appointments": "Citas",
            "Repeating appointment": "Cita periódica",
            "Blocked period": "Bloqueo",
            "Book even if it overlaps": "Reservar aunque se solape",
            "Dates and times": "Fechas y horas",
            "Asked by the customer": "Lo pide la clienta",
            "Applies from": "Se aplica desde",
            "Book from": "Reservar desde",
            "Book up to": "Reservar hasta",
            "Duplicate customer": "Ficha duplicada",
        }


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
