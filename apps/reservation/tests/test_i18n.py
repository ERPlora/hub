"""Every visible text of the reservation app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.operations import registry

from apps.reservation import queries, schemas, services
from apps.reservation.models import (
    BlockedDate,
    Reservation,
    Settings,
    TimeSlot,
    WaitlistEntry,
)
from base.tests.po import catalogue_key, po_entries

LOCALE = Path(apps.get_app_config("reservation").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Settings, TimeSlot, BlockedDate, Reservation, WaitlistEntry)


def lazy_constants(module) -> list:
    """Every module-level lazy text (``_("…")``) of ``module``."""
    return [
        value for value in vars(module).values() if type(value).__name__ == "__proxy__"
    ]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("reservation")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
    ]
    lazies += lazy_constants(queries) + lazy_constants(services) + lazy_constants(schemas)
    lazies += [message for message, _field in services.REFUSALS.values()]
    lazies += list(services.TARGET_WORDS.values())
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    for choices in (Reservation.Status, Reservation.Source):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | {"Reservation settings"} | schema_titles()


def schema_titles() -> set[str]:
    """The titles reservation's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. Only the ones reservation wrote: pydantic leaves ``title`` empty
    otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "reservation"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy] == []


#: Texts Reservas shows but Customers owns (its reason for a phone that is not a number of its country, RESERVATION-F06):
#: they are translated once, in Customers' catalog.
BORROWED = (services.PHONE_INVALID,)
CUSTOMER_LOCALE = Path(apps.get_app_config("customer").path) / "locale" / "es" / "LC_MESSAGES"


def test_every_visible_text_is_in_the_catalog():
    """Each text is looked up as the compiled catalogue keys it, context included: a ``pgettext_lazy`` that goes back
    to ``_()``, or whose context has a typo, is missing from the catalogue and Spanish says it in English or in
    another app's words (hub#638)."""
    texts = visible_texts()
    assert len(texts) > 100  # positive control: the collection found the app's texts...
    assert len({key for key in texts if "\x04" in key}) >= 15  # ...and kept the context of its pgettext_lazy ones
    with translation.override("en"):
        borrowed = {catalogue_key(text) for text in BORROWED}
    assert texts - borrowed - set(po_entries(LOCALE / "django.po")) == set()
    assert borrowed - set(po_entries(CUSTOMER_LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_the_card_says_each_title_with_reservations_own_spanish():
    """A title reservation shares with an app installed before it («Date» with Customers and Invoicing) is said with
    that app's Spanish, so reservation's own entry would be dead text: they have to say the same (hub#323)."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = schema_titles()
    assert {"Date", "Duplicate customer", "Book anyway"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("reservation")
        assert str(config.verbose_name) == "Reservas"
        assert [str(nav.label) for nav in config.navigation] == ["Reservas", "Lista de espera", "Disponibilidad"]
        assert [str(label) for label in Reservation.Status.labels] == [
            "Pendiente",
            "Confirmada",
            "Sentada",
            "Completada",
            "Cancelada",
            "No presentada",
        ]
        assert [str(label) for label in Reservation.Source.labels] == [
            "Teléfono",
            "En el local",
            "Lista de espera",
            "WhatsApp",
            "Internet",
        ]
        messages = {code: str(message) for code, (message, _field) in services.REFUSALS.items()}
        assert messages["phone_required"] == "Este negocio pide un teléfono en cada reserva."
        assert messages["date_blocked"] == (
            "Esa fecha está bloqueada (festivo o cierre): ese día no se aceptan reservas."
        )
        assert messages["outside_schedule"] == "A esa hora el negocio está cerrado."
        assert messages["no_service_day"] == "No hay servicio a esa hora: ninguna franja la cubre."
        assert messages["no_capacity"] == "Esa franja ya está completa para ese día."
        assert str(services.NOT_EDITABLE) == "Esta reserva ya no se puede cambiar: solo sus notas."
        assert str(services.ENTRY_CONVERTED) == "Esta entrada ya se convirtió en reserva."


def test_spanish_says_reservations_own_words_not_an_earlier_apps():
    """Two labels Reservas shares in English with an app loaded before it come out in Spanish with its own words,
    the ones its screens and WORKBOOK say: where a reservation came from is its «origen», not Citas' «reservada
    por»; the setting that asks for an email is «correo obligatorio», not Reservas online's «email obligatorio»
    (hub#548)."""
    labels = {
        "Reservation.source": Reservation._meta.get_field("source").verbose_name,
        "Settings.require_email": Settings._meta.get_field("require_email").verbose_name,
    }
    with translation.override("es"):
        assert {name: str(label) for name, label in labels.items()} == {
            "Reservation.source": "origen",
            "Settings.require_email": "correo obligatorio",
        }


def test_a_refusal_names_the_status_in_spanish():
    with translation.override("es"):
        label = str(Reservation.Status.CONFIRMED.label).lower()
        assert str(services.STEP_REFUSED) % {"status": label, "target": services.TARGET_WORDS["confirmed"]} == (
            "Esta reserva está confirmada: no se puede confirmar."
        )


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/reservation/reservations/confirm",
        json.dumps({"guest": "Nadie"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esa reserva no existe en este negocio."
