"""Models of the service settings: the rules the database itself keeps.

The operations check every rule first, with their own messages; these constraints are the last line
(the Django admin and two writes at once do not go through the operations' checks).
"""

from apps.service.models.settings import ServiceSettings
from apps.service.tests.conftest import HUB_DB, refused

pytestmark = HUB_DB


def test_the_settings_are_a_single_row_with_the_factory_values():
    first = ServiceSettings.objects.create()
    assert (
        first.default_duration,
        first.default_buffer_time,
        first.default_tax_category,
    ) == (60, 0, None)
    assert (first.show_prices, first.show_duration, first.allow_online_booking) == (
        True,
        True,
        True,
    )
    assert refused(model=ServiceSettings)


def test_a_settings_duration_of_zero_is_refused():
    assert refused(model=ServiceSettings, default_duration=0)
