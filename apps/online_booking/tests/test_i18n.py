"""Every visible text of the online booking app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.online_booking import queries, schemas, services
from apps.online_booking.models import Booking, Settings
from base.tests.po import po_entries

LOCALE = Path(apps.get_app_config("online_booking").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Settings, Booking)


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top, alone or as the values of a dict."""
    found = []
    for value in vars(module).values():
        items = value.values() if isinstance(value, dict) else (value,)
        found += [item for item in items if isinstance(item, Promise)]
    return found


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, messages) and the titles of its
    schemas."""
    config = apps.get_app_config("online_booking")
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
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles online_booking's operations give their input data (``gettext_noop``): the assistant's card names
    each datum by them, so each one needs its Spanish. Only the ones online_booking wrote: pydantic leaves ``title``
    empty otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "online_booking"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    assert len(visible_texts()) > 40  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_the_card_says_each_title_with_online_bookings_own_spanish():
    """A title online_booking shares with an app installed before it («Services» with Sales and Services) is said
    with that app's Spanish, so online_booking's own entry would be dead text: they have to say the same."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = schema_titles()
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
