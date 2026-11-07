"""Every visible text of the cart_checkout app has its Spanish translation, compiled and current (the old
module's `locales/es.json`, for the server's texts; the pages' texts are frontend/locale/locale.test.ts)."""

import gettext
from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.cart_checkout import admin as cart_admin
from apps.cart_checkout import queries, schemas, services
from apps.cart_checkout.models import Cart, CartItem, Order, OrderCounter
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    model_texts,
    module_texts,
    operation_titles,
    po_entries,
    untranslated,
)

LOCALE = Path(apps.get_app_config("cart_checkout").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Cart, CartItem, Order, OrderCounter)


def visible_texts() -> set[str]:
    """The catalogue key of every lazy text the app shows (menu, store, admin, choices, messages) — its English, with
    its context in front for a ``pgettext_lazy`` — and the titles of its schemas."""
    config = apps.get_app_config("cart_checkout")
    lazies = [*config_texts(config)]
    lazies += module_texts(queries, services, schemas, cart_admin)
    lazies += model_texts(MODELS)
    lazies += list(Cart.Status.labels) + list(Order.Status.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("cart_checkout")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """By its whole key, context included: a text that goes back to ``_()`` while its entry keeps the context, or whose
    context has a typo, is missing from the catalogue — on screen it says another app's Spanish (hub#652)."""
    texts = visible_texts()
    assert len(texts) > 60  # positive control: the collection found the app's texts...
    assert len({key for key in texts if "\x04" in key}) >= 18  # ...and kept the context of its pgettext_lazy ones
    assert texts - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_cart_checkouts_own_spanish():
    """A title cart_checkout shares with an app installed before it («Customer» with Tables) is said with that app's
    Spanish, so cart_checkout's own entry would be dead text: they have to say the same."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("cart_checkout")
    assert {"Customer", "Cart line", "Order"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def said_in_spanish(key: str) -> str:
    """How the Hub says a catalogue entry in Spanish: every app's catalogue merged, the first one to have it winning."""
    with translation.override("es"):
        if "\x04" in key:
            context, msgid = key.split("\x04", 1)
            return translation.pgettext(context, msgid)
        return translation.gettext(key)


def test_no_other_apps_catalogue_says_a_text_of_cart_checkout_its_own_way():
    """An order is a «pedido» here and an «orden» in the app installed before it; its payment method a «método de pago»
    here and a «medio de pago» at the till: an entry another catalogue also has, without its own context, was said the
    other app's way — in the admin and on every card that names a datum by its model."""
    entries = po_entries(LOCALE / "django.po")
    assert len(entries) > 60  # positive control: the catalogue was read
    shadowed = {key: said_in_spanish(key) for key, (msgstr, _) in entries.items() if said_in_spanish(key) != msgstr}
    assert shadowed == {}


def test_an_order_and_its_data_are_said_as_cart_checkout_says_them():
    """What the models call an order, a cart's items, the payment method and the moments of a cart and an order (a
    «pedido» is masculine: «pagado el», not «pagada el»), in both languages."""
    names = lambda: [  # noqa: E731
        str(Order._meta.verbose_name),
        str(Cart._meta.get_field("total_items").verbose_name),
        str(Cart._meta.get_field("deleted_at").verbose_name),
        str(Order._meta.get_field("payment_method").verbose_name),
        str(Order._meta.get_field("paid_at").verbose_name),
        str(Order._meta.get_field("failed_at").verbose_name),
        str(Order._meta.get_field("completed_at").verbose_name),
        str(schemas.EMAIL_INVALID),
        str(cart_admin.CHOOSE_A_HUB),
    ]
    with translation.override("es"):
        assert names() == [
            "pedido",
            "ítems",
            "borrado el",
            "método de pago",
            "pagado el",
            "fallido el",
            "completado el",
            "Introduce un email válido.",
            "Elige primero un hub (su enlace en el admin del SaaS): la acción se ejecuta en ese hub.",
        ]
    with translation.override("en"):
        assert names() == [
            "order",
            "items",
            "deleted at",
            "payment method",
            "paid at",
            "failed at",
            "completed at",
            "Enter a valid email.",
            "Choose a hub first (its link in the SaaS admin): the action runs on that hub.",
        ]


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
