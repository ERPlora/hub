"""Every visible text of the kitchen app has its Spanish translation, compiled and current."""

import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.operations import registry

from apps.kitchen import queries, schemas, services
from apps.kitchen.models import (
    CategoryRoute,
    DayCounter,
    Destination,
    ItemStatus,
    KitchenSettings,
    LogAction,
    LogEntry,
    OrderType,
    PrinterUsage,
    Priority,
    ProductRoute,
    SoundTone,
    Station,
    Ticket,
    TicketItem,
    TicketStatus,
)
from base.tests.po import catalogue_key, compiled_differences, model_texts, po_entries, untranslated

LOCALE = Path(apps.get_app_config("kitchen").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (
    Station,
    ProductRoute,
    CategoryRoute,
    KitchenSettings,
    DayCounter,
    Ticket,
    TicketItem,
    LogEntry,
)
CHOICES = (
    Destination,
    PrinterUsage,
    OrderType,
    Priority,
    SoundTone,
    TicketStatus,
    ItemStatus,
    LogAction,
)


def lazy_constants(module) -> list:
    return [
        value for value in vars(module).values() if type(value).__name__ == "__proxy__"
    ]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages, paper) and the
    titles of its schemas."""
    config = apps.get_app_config("kitchen")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
    ]
    lazies += (
        lazy_constants(queries) + lazy_constants(services) + lazy_constants(schemas)
    )
    lazies += model_texts(MODELS)
    for choices in CHOICES:
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles kitchen's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. Only the ones kitchen wrote: pydantic leaves ``title`` empty
    otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "kitchen"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """By its whole key, context included: a text that goes back to ``_()`` while its entry keeps the context, or whose
    context has a typo, is missing from the catalogue — on screen it says another app's Spanish (hub#659)."""
    texts = visible_texts()
    assert len(texts) > 140  # positive control: the collection found the app's texts...
    assert len({key for key in texts if "\x04" in key}) >= 6  # ...and kept the context of its pgettext_lazy ones
    assert texts - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("kitchen")
        assert str(config.verbose_name) == "Cocina"
        assert [str(nav.label) for nav in config.navigation] == [
            "Pantalla",
            "Comandas",
            "Estaciones",
            "Historial",
        ]
        assert str(services.INVALID_TRANSITION) == (
            "Esa comanda ya no está en el estado que requiere esta acción. Actualiza e inténtalo de nuevo."
        )
        assert (
            str(services.STATION_NAME_TAKEN)
            == "Ya hay una estación con ese nombre. Elige otro nombre."
        )
        assert (
            str(services.STATION_INACTIVE)
            == "Esa estación está desactivada: actívala o elige otra."
        )
        assert (
            str(services.AMBER_FIRST)
            == "El aviso ámbar tiene que llegar antes que el rojo."
        )
        assert str(services.URGENT) == "!! URGENTE !!"
        assert (
            str(services.VOIDED_DISH) % {"label": "Mesa 4"} == "PLATO ANULADO · Mesa 4"
        )
        assert str(queries.TICKET_NOT_FOUND) == "Esa comanda no existe en este negocio."
        assert [str(label) for label in TicketStatus.labels] == [
            "Por preparar",
            "En preparación",
            "Lista",
            "Servida",
            "Cancelada",
        ]
        assert [str(label) for label in OrderType.labels] == [
            "En sala",
            "Para llevar",
            "A domicilio",
        ]
        assert [str(label) for label in Priority.labels] == ["Normal", "Urgente", "VIP"]


def test_spanish_says_the_kitchens_own_words_not_an_earlier_apps():
    """The labels the kitchen shares in English with an app loaded before it come out in Spanish with the kitchen's
    words (hub#659): a voided dish is «Anulado», not Clientes' «Anulada»; a station is «activa», not Django's «activo»;
    a ticket is «empezada el» like it is «recibida el» and «servida el», not Asistencia's «empezó a las», and a ticket
    taken off is «borrada» as its History says, not Inventario's «eliminado». A station taken off is «eliminada», as the
    WORKBOOK says it («estación eliminada») and as it is «activa», not Inventario's masculine «eliminado»; who last
    changed a row reads «actualizado» like everywhere: the same words."""
    labels = {
        "ItemStatus.VOIDED": ItemStatus.VOIDED.label,
        "Station.is_active": Station._meta.get_field("is_active").verbose_name,
        "Station.is_deleted": Station._meta.get_field("is_deleted").verbose_name,
        "Station.deleted_at": Station._meta.get_field("deleted_at").verbose_name,
        "Ticket.started_at": Ticket._meta.get_field("started_at").verbose_name,
        "Ticket.is_deleted": Ticket._meta.get_field("is_deleted").verbose_name,
        "Ticket.deleted_at": Ticket._meta.get_field("deleted_at").verbose_name,
        "Ticket.updated_at": Ticket._meta.get_field("updated_at").verbose_name,
        "Ticket.updated_by": Ticket._meta.get_field("updated_by").verbose_name,
        "KitchenSettings.updated_at": KitchenSettings._meta.get_field("updated_at").verbose_name,
        "KitchenSettings.updated_by": KitchenSettings._meta.get_field("updated_by").verbose_name,
    }
    with translation.override("es"):
        assert {name: str(label) for name, label in labels.items()} == {
            "ItemStatus.VOIDED": "Anulado",
            "Station.is_active": "activa",
            "Station.is_deleted": "eliminada",
            "Station.deleted_at": "eliminada el",
            "Ticket.started_at": "empezada el",
            "Ticket.is_deleted": "borrada",
            "Ticket.deleted_at": "borrada el",
            "Ticket.updated_at": "actualizado el",
            "Ticket.updated_by": "actualizado por",
            "KitchenSettings.updated_at": "actualizado el",
            "KitchenSettings.updated_by": "actualizado por",
        }


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/kitchen/stations/delete",
        json.dumps({"station": "Nowhere"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"] == "Esa estación no existe en este negocio."
    )
