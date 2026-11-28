"""The till settings: one row at most, the factory values and the discount cap."""

from apps.sale.models.settings import Settings
from apps.sale.tests.conftest import HUB_DB, refused

pytestmark = HUB_DB


def test_only_one_settings_row():
    Settings.objects.create()
    refused(lambda: Settings.objects.create())


def test_a_settings_row_has_the_factory_values():
    settings = Settings()
    assert (settings.allow_cash, settings.allow_card, settings.allow_transfer) == (
        True,
        True,
        False,
    )
    assert (settings.show_products, settings.show_services) == (True, True)
    assert settings.require_customer is False
    assert settings.allow_discounts is True
    assert settings.max_discount_percent == 100
    assert settings.enable_parked_tickets is True
    assert settings.default_tax_included is True
    assert settings.auto_invoice_with_tax_id is False
    assert settings.default_document_type == "ticket"
    assert settings.receipt_header == settings.receipt_footer == ""


def test_the_discount_cap_is_a_percentage():
    refused(lambda: Settings.objects.create(max_discount_percent=101))
