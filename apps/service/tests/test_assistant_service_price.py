"""The assistant asks the price of a new service before its card, as it asks the price of a new product: a service
named without it draws no card and the model hears which datum is missing. Free is said as 0."""

import json

from live import assistant as shared
from live.operations import get


def required(name: str) -> list[str]:
    return shared.tool_spec(get(name))["parameters"]["required"]


def test_the_price_of_a_new_service_is_a_datum_its_tool_requires_as_a_new_products():
    assert "price" in required("inventory.product.create")
    assert "price" in required("service.service.create")


def test_a_new_service_called_without_its_price_draws_no_card_and_the_model_hears_which_datum_is_missing():
    create = get("service.service.create")
    refused = shared.invalid_arguments(create, {"name": "Corte y peinado"})
    assert (refused.outcome, refused.code) == ("error", "invalid_payload")
    assert set(json.loads(refused.content)["error"]["fields"]) == {"price"}
    assert shared.invalid_arguments(create, {"name": "Consulta", "price": 0}) is None
