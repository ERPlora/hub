"""Every visible text of the inventory app has its Spanish translation, compiled and current."""

import gettext
import json
import re
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from live.meta import Category as AppCategory
from live.operations import registry

from apps.inventory import queries, schemas, services
from apps.inventory.models import Category, Product, ProductCategory, RefundStock, SaleStock, Settings, StockMovement, Unit

LOCALE = Path(apps.get_app_config("inventory").path) / "locale" / "es" / "LC_MESSAGES"
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals or contexts (the header is skipped).

    Line based: an entry starts at its ``#`` comments or its ``msgid``, so a header that is not
    followed by a blank line is not merged with the first entry.
    """
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            entries[msgid] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = line.startswith("msgid ") or (line.startswith("#") and current == "msgstr")
        if starts_entry:
            flush()
            parts, fuzzy, current = {"msgid": [], "msgstr": []}, False, None
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


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
    for model in (Settings, Category, Product, ProductCategory, StockMovement, SaleStock, RefundStock):
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        # The primary key comes from live.models.UUIDModel; a reverse relation has no text of this app.
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
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
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


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
