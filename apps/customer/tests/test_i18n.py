"""Every visible text of the customer app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.errors import InvalidPayload

from apps.customer import models, queries, schemas, services
from base.tests.po import (
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    mo_entries,
    model_texts,
    module_texts,
    operation_titles,
    untranslated,
)

from .conftest import run

LOCALE = Path(apps.get_app_config("customer").path) / "locale" / "es" / "LC_MESSAGES"


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("customer")
    lazies = [
        *config_texts(config),
        *module_texts(schemas, queries, services),
    ]
    lazies += model_texts(config.get_models())
    for choices in (
        models.Customer.Stage,
        models.Customer.Source,
        models.Customer.PreferredChannel,
        models.CustomField.FieldType,
        models.Activity.Kind,
        models.Purchase.Status,
        models.Consent.Channel,
        models.Consent.State,
        models.Consent.Source,
        models.HealthRecord.TestResult,
    ):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | operation_titles("customer")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Clientes by its whole key, context included: a ``pgettext_lazy`` that goes back to ``_()``, or
    whose context has a typo, is missing from the catalogue, and Spanish says it in English (hub#975)."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=150, with_context=0) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_customers_own_spanish():
    """A title customer shares with another app («Duplicate customer» with Reservations) is said with the Spanish of
    whichever app Django merges last: if it is not customer's, customer's own entry is dead text (hub#323)."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("customer")
    assert {"Duplicate customer", "Groups", "Note"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("customer").verbose_name) == "Clientes"
        assert str(models.Customer.Stage.LEAD.label) == "Contacto"
        assert str(models.Customer.Source.WALK_IN.label) == "En el local"
        assert (
            str(queries.CUSTOMER_UNAVAILABLE) == "Este cliente ya no está disponible."
        )
        assert str(services.PHONE_INVALID) == (
            "No es un teléfono válido de su país: revisa las cifras o escríbelo con su prefijo "
            "internacional (+44…)."
        )
        assert (
            str(services.GROUP_NAME_TAKEN)
            == "Ya hay un grupo con ese nombre. Elige otro nombre."
        )
        assert (
            str(services.HEALTH_CONSENT_REQUIRED)
            == "Registra antes su permiso para guardar datos de salud."
        )
        assert str(models.HealthRecord.TestResult.NEGATIVE.label) == "Negativa"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/customer/customers",
        json.dumps({"name": "Ana", "phone": "600111"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"]["phone"].startswith(
        "No es un teléfono válido de su país"
    )


def compiled(path: Path) -> dict[str, str]:
    """The singular entries of a compiled catalogue, as Django reads them (the header left out)."""
    return {key: text for key, text in mo_entries(path).items() if isinstance(key, str)}


def test_what_an_earlier_app_also_translates_says_the_same_here():
    """Django joins every catalogue of a language in one, and the first app in ``INSTALLED_APPS`` wins a message
    two translate without context: ``live`` goes first, so the app's own wording never reached the user (a custom
    number field refused with live's «Introduce un número.», never with the app's); ``auth``'s «Correo
    electrónico» named the channel «Email» in the admin. What an app before this one says, this one says too."""
    configs = list(apps.get_app_configs())
    earlier = configs[: configs.index(apps.get_app_config("customer"))]
    ours = compiled(LOCALE / "django.mo")
    assert sorted(
        f"{message!r}: {config.label} «{text}», customer «{ours[message]}»"
        for config in earlier
        if (path := Path(config.path) / "locale" / "es" / "LC_MESSAGES" / "django.mo").exists()
        for message, text in compiled(path).items()
        if "\x04" not in message and message in ours and ours[message] != text
    ) == []


@pytest.mark.django_db
def test_a_custom_value_of_the_wrong_type_is_refused_in_spanish_under_its_field():
    """CUSTOMER-F04 «Si falla»: what the person reads in Spanish under each field."""
    visits = models.CustomField.objects.create(name="Visits", field_type="number")
    since = models.CustomField.objects.create(name="Since", field_type="date")
    ana = models.Customer.objects.create(name="Ana")
    sent = [
        {"field_id": visits.id, "value": "three"},
        {"field_id": since.id, "value": "2026-02-31"},
    ]
    with translation.override("es"):
        with pytest.raises(InvalidPayload) as refused:
            run("customer.customer.update", schemas.CustomerPatchIn(id=ana.id, field_values=sent))
        fields = {key: str(text) for key, text in refused.value.fields.items()}
    assert fields == {
        f"field_values.{visits.id}": "Introduce un número.",
        f"field_values.{since.id}": "Introduce una fecha válida.",
    }
    assert not models.CustomFieldValue.objects.filter(customer=ana).exists()


@pytest.mark.parametrize(
    ("key", "message"),
    [("invalidNumber", services.FIELD_INVALID_NUMBER), ("invalidDate", services.FIELD_INVALID_DATE)],
)
def test_what_the_card_cannot_read_is_worded_as_the_server_refuses_it(key, message):
    """A number or a date the browser cannot read is told by the form itself (it never reaches the server): in
    each language it says what the server says for the same value."""
    frontend = Path(apps.get_app_config("customer").path) / "frontend" / "locale"
    for language in ("en", "es"):
        texts = json.loads((frontend / f"{language}.json").read_text(encoding="utf-8"))
        with translation.override(language):
            assert texts["customer"]["form"][key] == str(message), language
