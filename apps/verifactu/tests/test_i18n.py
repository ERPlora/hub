"""Every visible text of the verifactu app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.invoice.tests.test_i18n import po_entries
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
    Record,
    SendControl,
)

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
    ]
    for model in (Config, Chain, SendControl, Record, Event, AeatRecord):
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
        ]
    with translation.override("en"):
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [
        msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy
    ] == []


def test_every_visible_text_is_in_the_catalog():
    catalog = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - catalog == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


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
