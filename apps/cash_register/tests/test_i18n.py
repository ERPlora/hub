"""Every visible text of the cash register app has its Spanish translation, compiled and current."""

import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise

from apps.cash_register import models, queries, schemas, services
from base.tests.po import catalogue_key as source
from base.tests.po import (
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    untranslated,
)

LOCALE = (
    Path(apps.get_app_config("cash_register").path) / "locale" / "es" / "LC_MESSAGES"
)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows: menu, store, admin, choices and messages."""
    config = apps.get_app_config("cash_register")
    lazies = [
        *config_texts(config),
    ]
    # The Home's step and panels (the old picker spoke Spanish to an English reader).
    lazies += [text for step in config.setup for text in (step.title, step.description)]
    lazies += [panel.title for panel in config.widgets]
    lazies += module_texts(queries, services, schemas, models)
    lazies += [text for text in model_texts(config.get_models()) if isinstance(text, Promise)]
    lazies += [
        *models.Session.Status.labels,
        *models.Movement.Type.labels,
        *models.Count.Type.labels,
        *(label for _, label, _ in services.REPORT_LINES),
    ]
    with translation.override("en"):
        return {source(text) for text in lazies} | operation_titles("cash_register")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Caja by its whole key, context included: a ``pgettext_lazy`` that goes back to ``_()``, or
    whose context has a typo, is missing from the catalogue, and Spanish says it in English (hub#975)."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=90, with_context=13) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("cash_register").verbose_name) == "Caja"
        assert (
            str(services.SESSION_ALREADY_OPEN)
            == "Ya hay una sesión de caja abierta. Ciérrala antes de abrir otra."
        )
        assert str(models.Movement.Type.OUT.label) == "Salida"


def test_spanish_says_the_cash_registers_own_words_not_an_earlier_apps():
    """Five labels the cash register shares in English with an app loaded before it (demo, customer, inventory,
    sale) come out in Spanish with its own words, the ones its WORKBOOK names: an open session is «Abierta» like a
    closed one is «Cerrada», not demo's «Abierto» (hub#660)."""
    labels = {
        "Session.status=open": models.Session.Status.OPEN.label,
        "Session.business_day": models.Session._meta.get_field("business_day").verbose_name,
        "SessionCounter.day": models.SessionCounter._meta.get_field("day").verbose_name,
        "Movement.method_name": models.Movement._meta.get_field("method_name").verbose_name,
        "Movement.sale_number": models.Movement._meta.get_field("sale_number").verbose_name,
        "Movement.created_by": models.Movement._meta.get_field("created_by").verbose_name,
    }
    with translation.override("es"):
        assert {name: str(label) for name, label in labels.items()} == {
            "Session.status=open": "Abierta",
            "Session.business_day": "día de negocio",
            "SessionCounter.day": "día de negocio",
            "Movement.method_name": "forma de pago",
            "Movement.sale_number": "número de venta",
            "Movement.created_by": "quién",
        }


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/cash_register/movements",
        json.dumps({"type": "in", "amount": 100}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "cash_register.no_open_session",
        "message": "No hay ninguna sesión de caja abierta: abre una primero.",
    }
