"""Every visible text of the cart_checkout app has its Spanish translation, compiled and current (the old
module's `locales/es.json`, for the server's texts; the pages' texts are frontend/locale/locale.test.ts)."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.cart_checkout import admin as cart_admin
from apps.cart_checkout import queries, schemas, services
from apps.cart_checkout.models import Cart, CartItem, Order, OrderCounter

LOCALE = Path(apps.get_app_config("cart_checkout").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Cart, CartItem, Order, OrderCounter)
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``key → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped).

    The key is the msgid, or ``context\x04msgid`` for an entry with a ``msgctxt`` (gettext's own key): the
    labels other apps also translate («Active», «Completed») carry a context, or the Spanish of the app
    listed first in INSTALLED_APPS would win.
    """
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        context = _unescape("".join(parts["msgctxt"]))
        if msgid:
            key = f"{context}\x04{msgid}" if context else msgid
            entries[key] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = (
            line.startswith("msgctxt ")
            or (line.startswith("msgid ") and current != "msgctxt")
            or (line.startswith("#") and current == "msgstr")
        )
        if starts_entry:
            flush()
            parts, fuzzy, current = ({"msgctxt": [], "msgid": [], "msgstr": []}, False, None)
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


def lazy_constants(module) -> list:
    """Every module-level lazy text (``_("…")``) of ``module``."""
    return [value for value in vars(module).values() if type(value).__name__ == "__proxy__"]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("cart_checkout")
    lazies = [config.verbose_name, config.summary, config.description, *(nav.label for nav in config.navigation)]
    lazies += lazy_constants(queries) + lazy_constants(services) + lazy_constants(schemas) + lazy_constants(cart_admin)
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    lazies += list(Cart.Status.labels) + list(Order.Status.labels)
    with translation.override("en"):
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    assert len(visible_texts()) > 60  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_of_the_workbook():
    config = apps.get_app_config("cart_checkout")
    with translation.override("es"):
        assert str(config.verbose_name) == "Carrito y pago"
        assert [str(nav.label) for nav in config.navigation] == ["Carritos", "Pedidos"]
        assert [str(label) for label in Cart.Status.labels] == ["Activo", "Abandonado", "Convertido", "Expirado"]
        assert [str(label) for label in Order.Status.labels] == ["Iniciado", "Pagado", "Fallido", "Completado"]
        assert str(services.SESSION_TAKEN) == "Ya hay un carrito con esa sesión."
        assert str(services.CART_NOT_ACTIVE) % {"status": "Abandonado"} == (
            "Este carrito ya no admite cambios: está Abandonado."
        )
        assert str(services.CART_EMPTY) == (
            "Este carrito no tiene líneas: añade un producto antes de iniciar el pedido."
        )
        assert str(queries.CART_NOT_FOUND) == "Ese carrito no existe en este negocio."
        assert str(cart_admin.ERASE) == "Borrar los datos personales de sus clientes"
        assert str(services.LINE_TOO_LARGE) == (
            "El total de esta línea (cantidad × precio) supera lo que cabe en un carrito."
        )
        assert str(queries.CART_AMBIGUOUS) % {"said": "Ana", "codes": "s1, s2"} == (
            "«Ana» encaja con varios carritos: s1, s2. Di cuál."
        )
