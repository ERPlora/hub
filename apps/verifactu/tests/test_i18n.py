"""Every visible text of the verifactu app has its Spanish translation, compiled and current."""

import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

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

APP = Path(apps.get_app_config("verifactu").path)
LOCALE = APP / "locale" / "es" / "LC_MESSAGES"


def visible_texts() -> set[str]:
    config = apps.get_app_config("verifactu")
    lazies = [
        *config_texts(config),
        # The Home's step of «Finish setting up your business» and its panels.
        *(text for step in config.setup for text in (step.title, step.description)),
        *(panel.title for panel in config.widgets),
        # The texts among a panel's literal props, as the one under the queue's figure.
        *(
            value
            for panel in config.widgets
            for value in panel.options.values()
            if type(value).__name__ == "__proxy__"
        ),
        *module_texts(queries, schemas, services, models, verifactu_admin),
        *EVENT_MESSAGES.values(),
        *WAIT_REASONS.values(),
        *Environment.labels,
        *Config.Route.labels,
        *Config.Representation.labels,
        *Config.HubStatus.labels,
        *Record.Type.labels,
        *Record.Status.labels,
        *Event.Kind.labels,
        *Event.Severity.labels,
        *OwnCertificate.Kind.labels,
    ]
    lazies += model_texts((Config, Chain, SendControl, Record, Event, AeatRecord, OwnCertificate))
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("verifactu")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of VeriFactu by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=200, with_context=12) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("verifactu").verbose_name) == "VeriFactu"
        assert str(Record.Status.PENDING.label) == "Pendiente"
        assert str(Record.Type.ANULACION.label) == "Anulación"
        assert str(Environment.TESTING.label) == "Pruebas (AEAT de pruebas)"
        assert str(services.NOT_IN_QUEUE).startswith("Este registro no está en la cola")


def test_verifactu_says_its_fields_with_the_aeats_words():
    """VeriFactu's Spanish is the AEAT's («subsanación», «fecha de expedición», «cuota»…, as its screens say), and the
    business's status is the account's («Activa», like «Suspendida»). An app installed before it that says the same
    English («Active» in customer, «correction» in attendance, «event» in flow, «issue date» and «rectification kind»
    in invoice, «tax» and «tax breakdown» in sale) spoke for it (hub#591)."""
    fields = {
        Record: ("issue_date", "rectification_kind", "tax_breakdown", "tax_amount", "correction"),
        AeatRecord: ("issue_date",),
    }
    with translation.override("es"):
        labels = {
            f"{model.__name__}.{name}": str(model._meta.get_field(name).verbose_name)
            for model, names in fields.items()
            for name in names
        }
        labels["Event"] = str(Event._meta.verbose_name)
        labels["Config.HubStatus.ACTIVE"] = str(Config.HubStatus.ACTIVE.label)
    assert labels == {
        "Record.issue_date": "fecha de expedición",
        "Record.rectification_kind": "tipo de rectificativa",
        "Record.tax_breakdown": "desglose",
        "Record.tax_amount": "cuota",
        "Record.correction": "subsanación",
        "AeatRecord.issue_date": "fecha de expedición",
        "Event": "evento",
        "Config.HubStatus.ACTIVE": "Activa",
    }


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
