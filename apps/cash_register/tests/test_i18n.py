"""Every visible text of the cash register app has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.cash_register import models, queries, schemas, services
from base.tests.po import catalogue_key, po_entries

LOCALE = (
    Path(apps.get_app_config("cash_register").path) / "locale" / "es" / "LC_MESSAGES"
)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows: menu, store, admin, choices and messages."""
    config = apps.get_app_config("cash_register")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
    ]
    # The Home's step and panels (gh:cash_register#123: the old picker spoke Spanish to an English reader).
    lazies += [text for step in config.setup for text in (step.title, step.description)]
    lazies += [panel.title for panel in config.widgets]
    for module in (queries, services, schemas, models):
        lazies += [
            value for value in vars(module).values() if isinstance(value, Promise)
        ]
    for model in config.get_models():
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
            and isinstance(field.verbose_name, Promise)
        ]
    lazies += [
        *models.Session.Status.labels,
        *models.Movement.Type.labels,
        *models.Count.Type.labels,
        *(label for _, label, _ in services.REPORT_LINES),
    ]
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles cash_register's operations give their input data, and the data of the answer a write's preview shows
    (BASE-F98): the assistant's card names each datum by them, so each one needs its Spanish. A title pydantic makes up
    from the field is not one."""
    titles = set()
    for op in registry.values():
        if op.app_label == "cash_register":
            shown = [op.input.model_json_schema().get("properties", {})]
            preview = (op.ai or {}).get("preview") if isinstance(op.ai, dict) else None
            if preview:
                answer = registry[preview["operation"]].output.model_json_schema().get("properties", {})
                shown.append({name: answer[name] for name in preview["fields"]})
            for props in shown:
                for name, prop in props.items():
                    title = prop.get("title")
                    if title and title != name.title().replace("_", " "):
                        titles.add(title)
    return titles


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [
        msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy
    ] == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


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
