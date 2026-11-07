"""Every visible text of the online booking app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.online_booking import queries, schemas, services
from apps.online_booking.models import Booking, Settings
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

LOCALE = Path(apps.get_app_config("online_booking").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Settings, Booking)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, messages) and the titles of its
    schemas."""
    config = apps.get_app_config("online_booking")
    lazies = [
        *config_texts(config),
        *module_texts(queries, services, schemas),
    ]
    lazies += model_texts(MODELS)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("online_booking")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Reservas online by its whole key, context included: a ``pgettext_lazy`` that goes back to
    ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English (hub#975)."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=45, with_context=1) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_online_bookings_own_spanish():
    """A title online_booking shares with an app installed before it («Services» with Sales and Services) is said
    with that app's Spanish, so online_booking's own entry would be dead text: they have to say the same."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("online_booking")
    assert {"Customer", "Services", "Slot interval (minutes)"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("online_booking")
        assert str(config.verbose_name) == "Reservas online"
        assert [str(nav.label) for nav in config.navigation] == ["Reservas", "Ajustes"]
        assert str(queries.PAGE_DISABLED) == "Este negocio no acepta reservas online ahora mismo."
        assert str(queries.BOOKING_NOT_FOUND) == "Esa reserva no existe o su enlace ya no es válido."
        assert str(queries.DEFAULT_TITLE) == "Reserva tu cita"
        assert str(services.TIME_TAKEN) == "Esa hora ya no está libre. Elige otra."
        assert str(services.DEFAULT_CONFIRMED) == "Tu reserva está confirmada. ¡Hasta pronto!"


@pytest.mark.django_db
def test_the_public_page_answers_in_the_visitors_language(client, make_user, salon):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.get("/api/online_booking/public/page", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert response.json()["title"] == "Reserva tu cita"
    refused = client.get(
        "/api/online_booking/bookings/detail", {"number": "APT-NOPE"}, HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es"
    )
    assert refused.status_code == 404
    assert refused.json()["error"]["message"] == "Esa reserva no existe o su enlace ya no es válido."
    assert json.dumps(refused.json())
