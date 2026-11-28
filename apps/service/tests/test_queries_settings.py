"""The settings of the service app: the factory ones until the business saves its own."""

from apps.service.models.settings import ServiceSettings

from .conftest import HUB_DB, run

pytestmark = HUB_DB


def test_the_settings_are_the_factory_ones_until_saved(tax):
    settings = run("service.settings.get")
    assert (
        settings.default_duration,
        settings.default_buffer_time,
        settings.default_tax_category_key,
    ) == (60, 0, None)
    assert (
        settings.show_prices,
        settings.allow_online_booking,
        settings.updated_at,
    ) == (True, True, None)
    ServiceSettings.objects.create(default_duration=45, default_tax_category=tax)
    settings = run("service.settings.get", role="hub_employee")
    assert (
        settings.default_duration,
        settings.default_tax_category_key,
        settings.default_tax_category_name,
    ) == (
        45,
        tax.key,
        tax.name,
    )
