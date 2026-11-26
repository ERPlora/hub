"""A service's price on the public booking page goes with how it is priced, and both hide together."""

import pytest

from apps.online_booking.service_price import ServicePriceOut, shown_price
from apps.service.models.catalog import Service


@pytest.mark.parametrize("pricing_type", ["fixed", "hourly", "from", "variable", "free"])
def test_a_shown_price_says_how_it_is_priced(pricing_type):
    service = Service(price=6500, pricing_type=pricing_type)
    assert shown_price(service, show_prices=True) == {"price": 6500, "pricing_type": pricing_type}


def test_a_business_that_hides_its_prices_hides_how_they_are_priced_too():
    service = Service(price=0, pricing_type="free")
    assert shown_price(service, show_prices=False) == {"price": None, "pricing_type": None}


def test_the_price_is_money_and_its_pricing_one_of_the_services():
    schema = ServicePriceOut.model_json_schema()
    assert schema["properties"]["price"]["money"] is True
    pricing = schema["properties"]["pricing_type"]["anyOf"][0]
    assert pricing["enum"] == ["fixed", "hourly", "from", "variable", "free"]
