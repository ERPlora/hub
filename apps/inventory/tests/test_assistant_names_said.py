"""How the model is told to name Inventory's records (INVENTORY-F29, F06): a product is looked up with the person's own
words first, never translated, for it has one name, in the language it was written in («Tarta de queso QA» was searched
as «cheesecake» and another product, the template's «Cheesecake», was marked sold out); only when nothing matches may it
be written in another language, and the model says which one it took (a bar's «caña» is its template's «Draught beer»:
it found it and asked instead of going on); and before creating a category it
looks at the ones there are, which may be written in another language (it made «Postres» beside the template's
«Desserts»). Field descriptions reach the model with each tool and never move a tool in the ranking.
"""

from live.assistant import input_schema
from live.operations import registry

from base import assistant

#: What every datum that names a product asks of the model.
IN_THEIR_WORDS = "in the person's own words, never translated"
#: The reads that look products up by a part of their name or SKU.
SEARCHES = ("inventory.product.list", "inventory.product.list_for_sale", "inventory.product.list_low_stock")


def inventory_tools():
    return [op for op in registry.values() if op.app_label == "inventory" and assistant.tools.is_tool(op)]


def properties(op) -> dict[str, list[dict]]:
    """Each datum the tool's input takes, at any depth (its lines' too), by its name."""
    schema = input_schema(op)
    found: dict[str, list[dict]] = {}
    for props in [schema.get("properties", {}), *(one.get("properties", {}) for one in schema.get("$defs", {}).values())]:
        for name, prop in props.items():
            found.setdefault(name, []).append(prop)
    return found


def test_every_tool_that_takes_a_product_by_its_name_asks_for_the_persons_own_words():
    taking = [op for op in inventory_tools() if "product" in properties(op)]
    assert len(taking) >= 8  # positive control: the product's writes and its stock's take one
    said = {prop.get("description", "") for op in taking for prop in properties(op)["product"]}
    assert len(said) == 1  # one text, wherever a product is named
    text = said.pop().lower()
    assert IN_THEIR_WORDS in text
    assert "only if none matches" in text and "another language" in text and "which one" in text


def test_every_search_of_products_asks_for_the_persons_own_words():
    for name in SEARCHES:
        props = properties(registry[name])
        assert IN_THEIR_WORDS in props["search"][0]["description"], name
    assert IN_THEIR_WORDS in properties(registry["inventory.product.list"])["name"][0]["description"]


def test_a_new_categorys_name_asks_to_look_first_at_the_ones_written_in_another_language():
    [prop] = properties(registry["inventory.category.create"])["name"]
    assert "inventory.category.list" in prop["description"] and "another language" in prop["description"]
