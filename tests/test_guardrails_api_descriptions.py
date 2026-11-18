"""The API's documentation speaks to whoever integrates, never in the words of the Hub's own code.

Every description of ``/api/openapi.json`` (and so of the Postman collection made from it) is read here. One may
name an operation (``base.app.get``: the ``operationId`` an integrator calls) or a value the API sends or takes, quoted
as «base.team»; it never names a module, a function or a constant of the Hub's code (``base.usage``,
``live.assistant.NAMED``): whoever integrates does not have that code, and the name stops existing as soon as the code
moves to another module.
"""

import re

import pytest
from live.operations import registry

from config.api import api

#: A dotted name that starts with one of the Hub's own Python packages: a piece of its code.
CODE_NAME = re.compile(r"(?<![\w.])(?:apps|base|config|control|live|shared)(?:\.[A-Za-z_]\w*)+")
#: A value the API sends or takes, quoted as the person reads it: data, not code.
API_VALUE = re.compile(r"«[^»]*»")


def code_names(text: str) -> list[str]:
    """The pieces of the Hub's code ``text`` names: dotted names that are neither an operation nor a quoted value."""
    return [name for name in CODE_NAME.findall(API_VALUE.sub("", text)) if name not in registry]


def descriptions(node: object, path: str) -> list[tuple[str, str]]:
    """``(where, text)`` of every description under ``node``, a part of an OpenAPI document found at ``path``."""
    if isinstance(node, list):
        return [found for index, item in enumerate(node) for found in descriptions(item, f"{path}[{index}]")]
    if not isinstance(node, dict):
        return []
    found = [(path, node["description"])] if isinstance(node.get("description"), str) else []
    return found + [item for key, value in node.items() for item in descriptions(value, f"{path}/{key}")]


def documented() -> list[tuple[str, str]]:
    """``(where, text)`` of every description ``/api/openapi.json`` carries.

    The whole document, not only its schemas: a query's fields reach it as the parameters of its operation, under
    ``paths``, and never as a schema of their own.
    """
    return descriptions(api.get_openapi_schema(), "")


def test_no_description_of_the_api_names_the_hubs_code():
    named = [(where, name) for where, text in documented() for name in code_names(text)]
    assert named == []


def test_the_query_parameters_of_an_operation_are_read_too():
    assert any("/parameters[" in where for where, _ in documented())


def test_a_schema_is_read_with_its_fields_and_their_alternatives():
    schema = {
        "description": "A call.",
        "properties": {"shown": {"description": "Its fingerprint."}, "money": {"anyOf": [{"description": "Its sum."}]}},
    }
    assert descriptions(schema, "/Call") == [
        ("/Call", "A call."),
        ("/Call/properties/shown", "Its fingerprint."),
        ("/Call/properties/money/anyOf[0]", "Its sum."),
    ]


@pytest.mark.parametrize(
    ("text", "names"),
    [
        (
            "The fingerprint of what the card of this call showed (``base.assistant.fingerprint``); empty while no "
            "card was drawn for it.",
            ["base.assistant.fingerprint"],
        ),
        ("The size of the business's own database, as the last night measured it (``base.usage``).", ["base.usage"]),
        ("without it, how many it carries (`live.assistant.NAMED`).", ["live.assistant.NAMED"]),
        ("Its price, as apps.sale.services.total adds it.", ["apps.sale.services.total"]),
        (
            "Moved by control.services.move, as config.settings says, with shared.models.",
            ["control.services.move", "config.settings", "shared.models"],
        ),
        ("``base.app.enable`` and ``base.app.disable``: one app of the business.", []),
        ("«<app>.<step>»: «base.apps», «base.mandatory.<app>» or «base.team».", []),
        ("catalog:<folder>/<name> (base.catalog_image.search, inventory.product.suggest_image), or empty.", []),
        ("The business's apps. Then its control. Live data comes base.", []),
        ("The taxable amount, as invoicing.base.total gives it, kept in its database.json.", []),
    ],
)
def test_a_code_name_is_told_from_an_operation_a_value_and_prose(text, names):
    assert code_names(text) == names
