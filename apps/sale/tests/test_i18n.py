"""Every visible text of the sale app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise

from apps.sale import models, pricing, queries, schemas, services

LOCALE = Path(apps.get_app_config("sale").path) / "locale" / "es" / "LC_MESSAGES"
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals or contexts (the header is skipped)."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            entries[msgid] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("msgid ") or (line.startswith("#") and current == "msgstr"):
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


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows: menu, store, the Home's panels, admin, choices and
    messages."""
    config = apps.get_app_config("sale")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *(widget.title for widget in config.widgets),
    ]
    for module in (queries, services, pricing, schemas, models):
        lazies += [
            value for value in vars(module).values() if isinstance(value, Promise)
        ]
    lazies += list(models.FACTORY_METHOD_NAMES.values())
    for model in apps.get_app_config("sale").get_models():
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
        *models.PaymentMethod.Type.labels,
        *models.Settings.DocumentType.labels,
        *models.Order.Status.labels,
        *models.Order.Source.labels,
        *models.Sale.Status.labels,
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
