"""Every visible text of Online orders has its Spanish translation, compiled and current."""

from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.online_order import services
from apps.online_order.models import Order, OrderLine, TableCode
from base.tests.po import compiled_differences, config_texts, missing_from_catalogue, model_texts, untranslated

LOCALE = Path(apps.get_app_config("online_order").path) / "locale" / "es" / "LC_MESSAGES"


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (the store, its permissions, the admin, what the table's
    page is told when its order is refused)."""
    lazies = [
        *config_texts(apps.get_app_config("online_order")),
        *model_texts((TableCode, Order, OrderLine)),
        services.TOO_MANY_ORDERS,
        services.NOT_ON_MENU,
    ]
    with translation.override("en"):
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=5, with_context=0) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_spanish_texts():
    config = apps.get_app_config("online_order")
    with translation.override("es"):
        assert str(config.verbose_name) == "Pedidos online"
        assert str(config.permissions["online_order.view_qr_code"]) == "Ver los QR de las mesas"
        assert str(config.permissions["online_order.change_qr_code"]) == "Regenerar los QR de las mesas"
        assert [str(nav.label) for nav in config.navigation] == ["Códigos QR"]
