"""Every visible text of the inventory app has its Spanish translation, compiled and current."""

import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from live.meta import Category as AppCategory
from live.operations import registry

from apps.inventory import queries, schemas, services
from apps.inventory.models import Category, Product, ProductCategory, RefundStock, SaleStock, Settings, StockMovement, Unit
from base.tests.po import compiled_differences, model_texts, po_entries, untranslated

LOCALE = Path(apps.get_app_config("inventory").path) / "locale" / "es" / "LC_MESSAGES"


def lazy_constants(module) -> list:
    """Every module-level lazy text (``_("…")``) of ``module``, alone or in a tuple."""
    lazies = []
    for value in vars(module).values():
        for item in value if isinstance(value, tuple) else (value,):
            if type(item).__name__ == "__proxy__":
                lazies.append(item)
    return lazies


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages, CSV)."""
    config = apps.get_app_config("inventory")
    lazies = [config.verbose_name, config.summary, config.description, *(nav.label for nav in config.navigation)]
    # The Home's step and panels (gh:hub#868: the old checklist spoke English to a Spanish reader).
    lazies += [text for step in config.setup for text in (step.title, step.description)]
    lazies += [panel.title for panel in config.widgets]
    lazies += lazy_constants(queries) + lazy_constants(services) + lazy_constants(schemas)
    lazies += model_texts((Settings, Category, Product, ProductCategory, StockMovement, SaleStock, RefundStock))
    for choices in (Unit, Product.Type, StockMovement.Type, SaleStock.State):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles inventory's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. A title pydantic makes up from the field is not one."""
    titles = set()
    for op in registry.values():
        if op.app_label == "inventory":
            for name, prop in op.input.model_json_schema().get("properties", {}).items():
                title = prop.get("title")
                if title and title != name.title().replace("_", " "):
                    titles.add(title)
    return titles


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


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
