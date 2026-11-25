"""The book's rules (``reservation.settings.get``)."""

from .conftest import HUB_DB, run, set_rules

pytestmark = HUB_DB


def test_the_settings_are_the_factory_ones_until_saved_with_the_business_zone():
    settings = run("reservation.settings.get")
    assert (settings.require_phone, settings.max_party_size, settings.timezone) == (
        True,
        20,
        "Europe/Madrid",
    )
    set_rules(max_party_size=12, auto_confirm=True)
    settings = run("reservation.settings.get")
    assert (settings.max_party_size, settings.auto_confirm) == (12, True)
