"""Every visible text of the invoice app has its Spanish translation, compiled and current."""

import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.core.validators import RegexValidator
from django.utils import translation
from live.operations import get, registry

from apps.invoice import platform, queries, schemas, services
from apps.invoice.models import (
    FACTORY_SERIES_NAMES,
    Invoice,
    InvoiceLine,
    InvoiceSeries,
    InvoiceType,
    Issuer,
)
from apps.invoice.tests.conftest import ctx_for, run
from base import assistant
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

APP = Path(apps.get_app_config("invoice").path)
LOCALE = APP / "locale" / "es" / "LC_MESSAGES"
TEMPLATE = APP / "templates" / "invoice" / "invoice.html"
SCREENS = json.loads((APP / "frontend" / "locale" / "es.json").read_text(encoding="utf-8"))["invoice"]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, Home, admin, choices, errors, paper)."""
    config = apps.get_app_config("invoice")
    lazies = [
        *config_texts(config),
        # The Home's steps: base paints them in the reader's language.
        *(text for step in config.setup for text in (step.title, step.description)),
        *module_texts(queries, schemas, services, platform),
        *(label for _english, label in FACTORY_SERIES_NAMES.values()),
        *(
            v.message
            for v in InvoiceSeries._meta.get_field("code").validators
            if isinstance(v, RegexValidator)
        ),
        *InvoiceType.labels,
        *Invoice.Status.labels,
        *Invoice.Source.labels,
        *Invoice.RectificationKind.labels,
        *Issuer.Source.labels,
    ]
    lazies += model_texts((InvoiceSeries, Issuer, Invoice, InvoiceLine))
    template = TEMPLATE.read_text(encoding="utf-8")
    with translation.override("en"):
        return (
            {catalogue_key(text) for text in lazies}
            | set(re.findall(r'{% translate "([^"]+)" %}', template))
            | operation_titles("invoice")
        )


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Facturación by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=150, with_context=9) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("invoice").verbose_name) == "Facturación"
        assert (
            str(queries.CANNOT_RECTIFY_RECTIFICATION)
            == "Una rectificativa no se puede rectificar."
        )
        assert str(queries.ALREADY_CANCELLED) == "La factura ya está cancelada."
        assert str(Invoice.Status.ISSUED.label) == "Emitida"
        assert str(queries.DOC_SIMPLIFIED) == "Factura simplificada"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/invoice/invoices",
        json.dumps(
            {
                "lines": [
                    {
                        "description": "x",
                        "quantity": "1",
                        "unit_price": 1,
                        "tax_rate": "21",
                    }
                ]
            }
        ),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    assert response.json()["error"]["message"].startswith("Configura el emisor")


# Django joins every app's Spanish catalogue and the first that translates a message wins, so a text invoice says
# with its own words reads another app's when that app comes earlier (base/tests/test_locale_modules.py).


def test_a_series_an_issuer_and_an_invoice_say_their_own_words_in_spanish():
    """As the admin shows them: a series is «activa», «creada el», «actualizada por»… (a series, never demo's or
    auth's «creado el», «activo»), the issuer's tax ID is «NIF» and its address «domicilio» (never customer's
    «NIF/CIF» and «dirección»), and the issuer, a masculine word, «actualizado el» and «actualizado por»."""

    def said(model, *names: str) -> dict[str, str]:
        return {name: str(model._meta.get_field(name).verbose_name) for name in names}

    with translation.override("es"):
        assert said(InvoiceSeries, "is_active", "created_at", "created_by", "updated_at", "updated_by") == {
            "is_active": "activa",
            "created_at": "creada el",
            "created_by": "creada por",
            "updated_at": "actualizada el",
            "updated_by": "actualizada por",
        }
        assert said(Issuer, "tax_id", "address", "updated_at", "updated_by") == {
            "tax_id": "NIF",
            "address": "domicilio",
            "updated_at": "actualizado el",
            "updated_by": "actualizado por",
        }
        assert said(Invoice, "updated_at") == {"updated_at": "actualizada el"}


def test_the_card_says_a_series_active_and_the_issuer_s_tax_id_and_address_as_their_screens_do():
    """The assistant's card names these data by their models' names: «Activa» as the series form says it, «NIF» and
    «Domicilio» as the Issuer screen does, never auth's «Activo» nor customer's «NIF/CIF» and «Dirección»."""

    def card(name: str) -> dict[str, str]:
        op = get(name)
        arguments = dict.fromkeys(op.input.model_json_schema()["properties"], "x")
        return {field["name"]: field["label"] for field in assistant.card(op, arguments, "es")["fields"]}

    for name in ("invoice.series.create", "invoice.series.update"):
        assert card(name)["is_active"] == SCREENS["series"]["form"]["active"] == "Activa", name
    for name in ("invoice.issuer.update", "invoice.issuer.sync"):
        said = card(name)
        assert (said["tax_id"], said["address"]) == (
            SCREENS["issuer"]["fields"]["taxId"],
            SCREENS["issuer"]["fields"]["address"],
        ) == ("NIF", "Domicilio"), name


@pytest.mark.django_db
def test_the_printed_breakdown_says_exempt_and_not_subject_as_the_invoice_screen_does(issuer):
    """The A4 paper's breakdown (INVOICE-F18) in Spanish: an exempt line «Exento» and one not subject «No sujeto», as
    the invoice's screen says them, never taxes' «Exenta» and «No sujeta»."""
    for category, operation_class in (("product.generic", "exempt"), ("service.generic", "not_subject")):
        run(
            "tax.rule.create",
            {
                "country_code": "ES",
                "region_code": "ES-CN",
                "tax_category_key": category,
                "rate_pct": "0",
                "tax_type": "igic",
                "operation_class": operation_class,
            },
        )
    run("tax.settings.update", {"region_code": "ES-CN"})
    invoice = run(
        "invoice.invoice.create",
        {
            "customer_name": "Talleres Pérez SL",
            "customer_tax_id": "B12345674",
            "customer_address": "Calle Luna 3",
            "lines": [
                {"description": "Book", "quantity": "1", "unit_price": 1000, "tax_category_key": "product.generic"},
                {"description": "Advice", "quantity": "1", "unit_price": 2000, "tax_category_key": "service.generic"},
            ],
        },
    )
    assert sorted(entry.qualification for entry in invoice.tax_breakdown) == ["exempt", "not_subject"]
    html = run("invoice.invoice.document", {"number": invoice.number}, ctx_for(language="es")).html
    # Each breakdown row of the totals: its label, then its base in brackets.
    rows = re.findall(r'<td class="muted">\s*([^<]+?)\s*<span class="muted">\(', html)
    assert (SCREENS["taxes"]["exempt"], SCREENS["taxes"]["notSubject"]) == ("Exento", "No sujeto")
    assert {"Exento", "No sujeto"} <= set(rows)
    assert not {"Exenta", "No sujeta"} & set(rows)
