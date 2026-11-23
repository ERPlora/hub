"""What the assistant is told when it creates or changes a kitchen station, so it answers what the Stations screen says.

Asked «Set up two kitchen stations: Cocina for the food and Barra for the drinks», the model created both and answered
«Both are active, so new dishes will go to them»: the station's ``is_active`` told it «Whether new dishes go to it» and
the result said true. A dish goes to a station only through the routing of its product or of its category, and whatever
has no route goes to «No station», as the routing panel of the Stations screen says while nothing is routed.

Nothing here runs an operation: the tests read what the model is told of each tool.
"""

import json
from pathlib import Path

import pytest
from live.assistant import tool_spec
from live.operations import registry

from apps.kitchen.schemas import StationOut

LOCALE = Path(__file__).resolve().parents[1] / "frontend" / "locale"
SWITCHED_ON = "Switched on: it gets only the products and categories routed to it."


def screen(language: str, key: str) -> str:
    """A label of Kitchen's screens, by its dotted key under ``kitchen`` in the app's catalogue of ``language``."""
    node = json.loads((LOCALE / f"{language}.json").read_text(encoding="utf-8"))["kitchen"]
    for part in key.split("."):
        node = node[part]
    return node


def told_of(name: str) -> dict:
    return tool_spec(registry[name])


def test_the_stations_screen_says_what_has_no_route_goes_to_no_station_in_english_and_spanish():
    assert screen("en", "routing.empty") == "Nothing routed yet: everything goes to «No station»."
    assert screen("es", "routing.empty") == "Nada enrutado todavía: todo sale en «Sin estación»."


def test_creating_a_station_tells_the_model_it_gets_nothing_until_something_is_routed_to_it():
    told = told_of("kitchen.station.create")["description"]

    assert "A new station gets nothing until products or categories are routed to it" in told
    assert f"whatever has no route goes to «{screen('en', 'display.stationNone')}»" in told


def test_creating_a_station_tells_the_model_to_offer_the_routing_rather_than_send_to_a_screen():
    told = told_of("kitchen.station.create")["description"]

    assert "say that nothing goes to it yet and offer to route the products or categories it should get" in told


@pytest.mark.parametrize("name", ["kitchen.station.create", "kitchen.station.update"])
def test_switching_a_station_on_does_not_tell_the_model_that_dishes_go_to_it(name):
    assert told_of(name)["parameters"]["properties"]["is_active"]["description"] == SWITCHED_ON


def test_the_station_a_write_returns_says_the_same_of_being_switched_on():
    assert StationOut.model_json_schema()["properties"]["is_active"]["description"] == SWITCHED_ON
