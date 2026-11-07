"""Every visible text of the sale app has its Spanish translation, compiled and current."""

import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.sale import models, pricing, queries, schemas, services
from base.tests.po import catalogue_key, compiled_differences, model_texts, po_entries, untranslated

LOCALE = Path(apps.get_app_config("sale").path) / "locale" / "es" / "LC_MESSAGES"


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows: menu, store, the Home's panels, the manager's approvals
    (with their figures), admin, choices and messages."""
    config = apps.get_app_config("sale")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *(widget.title for widget in config.widgets),
        *config.approvals.values(),
        *(sentence for sentences in getattr(config, "approval_figures", {}).values() for sentence in sentences),
    ]
    for module in (queries, services, pricing, schemas, models):
        lazies += [
            value for value in vars(module).values() if isinstance(value, Promise)
        ]
    lazies += list(models.FACTORY_METHOD_NAMES.values())
    lazies += [text for text in model_texts(apps.get_app_config("sale").get_models()) if isinstance(text, Promise)]
    lazies += [
        *models.PaymentMethod.Type.labels,
        *models.Settings.DocumentType.labels,
        *models.Order.Status.labels,
        *models.Order.Source.labels,
        *models.Sale.Status.labels,
    ]
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles sale's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. Only the ones sale wrote: pydantic leaves ``title`` empty otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "sale"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("sale").verbose_name) == "Ventas / TPV"
        assert str(models.FACTORY_METHOD_NAMES["Cash"]) == "Efectivo"
        assert str(models.FACTORY_METHOD_NAMES["Card"]) == "Tarjeta"
        assert (
            str(services.CUSTOMER_REQUIRED)
            == "Este negocio exige un cliente en cada venta."
        )
        assert (
            str(services.DISCOUNTS_NOT_ALLOWED) == "Este negocio no permite descuentos."
        )
        # SALE-F27 and F32 (WORKBOOK).
        assert str(services.VOUCHER_NEEDS_ONE_UNIT) == (
            "Un bono paga una línea de una unidad: separa la línea antes."
        )
        assert str(services.REFUND_NOTHING) == (
            "Una devolución tiene que devolver dinero o la sesión de un bono."
        )
        assert str(queries.SERVICES_UNAVAILABLE).startswith(
            "Servicios no está activa en este negocio"
        )
        # FIX-SALE-TABBAR-LABEL: the open price's families are «secciones» everywhere the user reads.
        assert str(queries.DEPARTMENT_NOT_FOUND) == (
            "Esa sección ya no está en este negocio. Recarga la lista y vuelve a intentarlo."
        )
        assert str(schemas.SAY_WHICH_DEPARTMENT_ROW) == (
            "Di qué sección: su id o su nombre."
        )


def test_spanish_says_ventas_own_words_not_an_earlier_apps():
    """The labels Ventas shares in English with an app loaded before it come out in Spanish with its own words
    (hub#560): an open check is «Abierta» like a «Completada» or «Anulada» one, not Demo's «Abierto»; what a line
    carries of Modifiers is its «suplementos» (SALE-F11, and «suplementos en línea propia» beside it), not Clientes'
    «opciones»; a sale is «anulada el» like it is «anulada por», not Clientes' «anulado el»."""
    labels = {
        "Order.status=open": models.Order.Status.OPEN.label,
        "OrderLine.modifiers": models.OrderLine._meta.get_field("modifiers").verbose_name,
        "SaleLine.modifiers": models.SaleLine._meta.get_field("modifiers").verbose_name,
        "Sale.voided_at": models.Sale._meta.get_field("voided_at").verbose_name,
    }
    with translation.override("es"):
        assert {name: str(label) for name, label in labels.items()} == {
            "Order.status=open": "Abierta",
            "OrderLine.modifiers": "suplementos",
            "SaleLine.modifiers": "suplementos",
            "Sale.voided_at": "anulada el",
        }


def test_a_line_names_the_product_data_it_freezes_as_inventory_names_them():
    """A line keeps a frozen copy of its product's category and of the quantity and unit its price refers to: the same
    data as Inventory's product, said with Inventory's words in Ventas' own catalogue too, so Spanish reads them alike
    whichever app is loaded first (hub#560: Ventas said «categoría de producto», «cantidad del precio» and «unidad del
    precio» while the screen showed Inventory's)."""
    own = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    said = {
        "product category": "categoría del producto",
        "price quantity": "cantidad de precio",
        "pricing unit": "unidad de precio",
    }
    assert {msgid: own.get(msgid) for msgid in said} == said
    fields = {"category_id": "product category", "price_quantity": "price quantity", "pricing_unit": "pricing unit"}
    with translation.override("es"):
        for model in (models.OrderLine, models.SaleLine):
            shown = {name: str(model._meta.get_field(name).verbose_name) for name in fields}
            assert shown == {name: said[msgid] for name, msgid in fields.items()}, model.__name__


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/sale/sales/void",
        json.dumps({"sale": "20990101-0001", "reason": "x"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "sale.sale_not_found",
        "message": "Esa venta no existe.",
    }


# The menu entry's key in apps.py → its tab's key in the frontend catalogues (`sale.tabs.*`).
TAB_KEYS = {
    "pos": "pos",
    "sales": "sales",
    "quick_notes": "quickNotes",
    "departments": "departments",
    "settings": "settings",
}


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_menu_and_the_tabbar_name_each_section_alike(language):
    # FIX-SALE-TABBAR-LABEL: a menu entry and its footer tab say the same word. «Sections» took the
    # place of «Departments», one word wider than a fifth of a phone's tabbar.
    frontend = Path(apps.get_app_config("sale").path) / "frontend" / "locale"
    catalogue = json.loads((frontend / f"{language}.json").read_text(encoding="utf-8"))
    tabs = catalogue["sale"]["tabs"]
    with translation.override(language):
        menu = {
            entry.id: str(entry.label)
            for entry in apps.get_app_config("sale").navigation
        }
    assert menu == {entry: tabs[key] for entry, key in TAB_KEYS.items()}
    assert menu["departments"] == {"en": "Sections", "es": "Secciones"}[language]
