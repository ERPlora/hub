"""The input schemas of the routing: one product or one category goes to one station."""

import uuid

import pytest
from pydantic import ValidationError

from apps.kitchen.schemas.fields import SAY_PRODUCT_OR_CATEGORY
from apps.kitchen.schemas.routing import RoutingClearIn, RoutingSetIn

from .test_schemas_fields import refuses


def test_a_route_goes_to_one_station_from_one_product_or_one_category():
    product = str(uuid.uuid7())
    data = RoutingSetIn.model_validate(
        {"station": "Grill", "product_id": product}
    )
    assert data.product_id and data.category_id is None
    assert refuses(RoutingSetIn, station="Grill")
    assert refuses(
        RoutingSetIn, station="Grill", product_id=product, category="Mains"
    )
    assert refuses(RoutingSetIn, product_id=product)
    assert refuses(RoutingClearIn)


def test_a_route_with_nothing_said_asks_first_for_what_it_routes():
    with pytest.raises(ValidationError) as refused:
        RoutingSetIn.model_validate({})
    (error,) = refused.value.errors()
    assert error["msg"].endswith(str(SAY_PRODUCT_OR_CATEGORY))
