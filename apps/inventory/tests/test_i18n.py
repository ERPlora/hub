"""Every visible text of the inventory app has its Spanish translation, compiled and current."""

import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from live.meta import Category as AppCategory

from apps.inventory import queries, schemas, services
from apps.inventory.models import Category, Product, ProductCategory, RefundStock, SaleStock, Settings, StockMovement, Unit
from base.tests.po import (
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    untranslated,
)

LOCALE = Path(apps.get_app_config("inventory").path) / "locale" / "es" / "LC_MESSAGES"


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages, CSV)."""
    config = apps.get_app_config("inventory")
    lazies = [*config_texts(config)]
    # The Home's step and panels (the old checklist spoke English to a Spanish reader).
    lazies += [text for step in config.setup for text in (step.title, step.description)]
    lazies += [panel.title for panel in config.widgets]
    lazies += module_texts(queries, services, schemas)
    lazies += model_texts((Settings, Category, Product, ProductCategory, StockMovement, SaleStock, RefundStock))
    for choices in (Unit, Product.Type, StockMovement.Type, SaleStock.State):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | operation_titles("inventory")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Inventario by its whole key, context included: a ``pgettext_lazy`` that goes back to ``_()``, or
    whose context has a typo, is missing from the catalogue, and Spanish says it in English (hub#975)."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=110, with_context=0) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        assert str(apps.get_app_config("inventory").verbose_name) == "Inventario"
        assert str(queries.PRODUCT_NOT_FOUND) == "Este producto no existe en este hub."
        assert str(services.SKU_TAKEN) == "Ese SKU ya existe en el catálogo"
        assert str(services.EAN13_TAKEN) == "Ese EAN-13 ya lo tiene otro producto del catálogo"
        assert str(services.INSUFFICIENT_STOCK) == "No hay stock suficiente para completar la operación."
        assert str(services.SERVICE_HAS_NO_STOCK) == "Un servicio no lleva stock."
        assert str(services.ROW_NAME_OR_SKU_MISSING) == "Faltan nombre o SKU"
        assert str(services.ROW_PRICE_NOT_NUMERIC) == "Precio no numérico"
        assert str(services.ROW_SKU_REPEATED) == "SKU duplicado en el fichero"
        assert str(services.ROW_OFF_GRID) == "La cantidad no respeta el incremento permitido para esta unidad"
        assert str(services.ROW_TAX_CATEGORY_MISSING) == "Falta la categoría fiscal"
        assert str(services.ROW_NAME_MISSING) == "Falta el nombre"
        assert [str(label) for label in StockMovement.Type.labels] == ["Inicial", "Recepción", "Venta", "Anulación", "Recuento", "Descuento", "Devolución"]
        assert str(Unit.HOUR.label) == "Hora (h)"
        assert str(AppCategory.CATALOG.label)  # the apps page's group comes from live, not from here


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/inventory/stock/count",
        json.dumps({"product_id": str(uuid.uuid7()), "stock": "1", "reason": "count"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Este producto no existe en este hub."
