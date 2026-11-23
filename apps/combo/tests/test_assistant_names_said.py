"""How the model is told to name a product of Inventory in Menus and combos (COMBO-F06): with the person's own words,
never translated, for a product has one name, in the language it was written in («the croquettes» became «Croquetas»
and the card named a product the business does not have: its is «Home-made croquettes»). Field descriptions reach the
model with each tool and never move a tool in the ranking.
"""

from live.assistant import input_schema
from live.operations import registry

from base import assistant

IN_THEIR_WORDS = "in the person's own words, never translated"


def products_named(op) -> list[dict]:
    """Each datum named ``product`` the tool's input takes, at any depth."""
    schema = input_schema(op)
    every = [schema.get("properties", {}), *(one.get("properties", {}) for one in schema.get("$defs", {}).values())]
    return [props["product"] for props in every if "product" in props]


def test_every_tool_of_menus_that_takes_a_product_by_its_name_asks_for_the_persons_own_words():
    tools = [op for op in registry.values() if op.app_label == "combo" and assistant.tools.is_tool(op)]
    taking = {op.name: products_named(op) for op in tools if products_named(op)}
    assert {"combo.option.create", "combo.option.update", "combo.combo.resolve"} <= set(taking)  # positive control
    for name, props in taking.items():
        for prop in props:
            assert IN_THEIR_WORDS in prop.get("description", ""), name
