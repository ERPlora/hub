"""Every visible text of the verifactu app has its Spanish translation, compiled and current."""

import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.operations import registry

from apps.verifactu import admin as verifactu_admin
from apps.verifactu import models, queries, schemas, services
from apps.verifactu.models import (
    EVENT_MESSAGES,
    WAIT_REASONS,
    AeatRecord,
    Chain,
    Config,
    Environment,
    Event,
    OwnCertificate,
    Record,
    SendControl,
)
from base.tests.po import catalogue_key, compiled_differences, missing_from_catalogue, model_texts, untranslated

APP = Path(apps.get_app_config("verifactu").path)
LOCALE = APP / "locale" / "es" / "LC_MESSAGES"


def messages_of(module) -> list:
    lazies = [
        value
        for name, value in vars(module).items()
        if name.isupper() and type(value).__name__ == "__proxy__"
    ]
    for name, value in vars(module).items():
        if name.isupper() and isinstance(value, dict):
            lazies += [
                item for item in value.values() if type(item).__name__ == "__proxy__"
            ]
    return lazies


def visible_texts() -> set[str]:
    config = apps.get_app_config("verifactu")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        # The Home's step of «Finish setting up your business» and its panels (FIX-VERIFACTU-SETUP-HOOKS).
        *(text for step in config.setup for text in (step.title, step.description)),
        *(panel.title for panel in config.widgets),
        # The texts among a panel's literal props, as the one under the queue's figure
        # (FIX-HUB-HOME-WIDGET-OPTIONS-LAZY-TEXT).
        *(
            value
            for panel in config.widgets
            for value in panel.options.values()
            if type(value).__name__ == "__proxy__"
        ),
        *messages_of(queries),
        *messages_of(schemas),
        *messages_of(services),
        *messages_of(models),
        *messages_of(verifactu_admin),
        *EVENT_MESSAGES.values(),
        *WAIT_REASONS.values(),
        *Environment.labels,
        *Config.Route.labels,
        *Config.Representation.labels,
        *Record.Type.labels,
        *Record.Status.labels,
        *Event.Kind.labels,
        *Event.Severity.labels,
        *OwnCertificate.Kind.labels,
    ]
    lazies += model_texts((Config, Chain, SendControl, Record, Event, AeatRecord, OwnCertificate))
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles verifactu's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. A title pydantic makes up from the field is not one."""
    titles = set()
    for op in registry.values():
        if op.app_label == "verifactu":
            for name, prop in op.input.model_json_schema().get("properties", {}).items():
                title = prop.get("title")
                if title and title != name.title().replace("_", " "):
                    titles.add(title)
    return titles


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of VeriFactu by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=200, with_context=5) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("verifactu").verbose_name) == "VeriFactu"
        assert str(Record.Status.PENDING.label) == "Pendiente"
        assert str(Record.Type.ANULACION.label) == "Anulación"
        assert str(Environment.TESTING.label) == "Pruebas (AEAT de pruebas)"
        assert str(services.NOT_IN_QUEUE).startswith("Este registro no está en la cola")


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(
    client, make_user, issuer, settings
):
    settings.VERIFACTU_GATEWAY_URL = ""
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/verifactu/contingency/retry",
        json.dumps({"invoice_number": "NOPE"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Registro no encontrado."
