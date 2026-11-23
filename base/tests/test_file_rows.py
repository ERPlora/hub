"""The card of an import from a file through the assistant: the rows it will create, each by the name its row gives,
never «File rows: 2 items» — the person can only check what they are told (hub#2241)."""

import pytest
from live.assistant import NAMED
from live.operations import get, registry

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.card_values import ctx

__all__ = ["in_business_a"]

#: The writes that create what the rows of a file carry, and a row of each as the import screen sends it.
IMPORTS = {
    "inventory.category.bulk_create": {"line": 1, "name": "Cucharas QA", "tax_category_key": "restaurant.food"},
    "inventory.product.bulk_create": {"line": 1, "name": "Cucharas QA", "sku": "CU-1", "price": "2,20"},
    "customer.customer.import": {"name": "Cucharas QA", "email": "ana@example.com", "phone": "600000000"},
}


def rows_field(write: str, rows: list, language: str = "es") -> dict:
    card = assistant.cards.card(get(write), {"rows": rows}, language, ctx({"*"}, language=language))
    return next(field for field in card["fields"] if field["name"] == "rows")


def tool_writes_with_rows() -> set[str]:
    return {
        op.name
        for op in registry.values()
        if op.kind == "command" and assistant.tools.is_tool(op) and "rows" in op.input.model_json_schema()["properties"]
    }


def test_every_write_the_assistant_offers_on_the_rows_of_a_file_is_one_of_the_imports():
    """A new import that takes rows comes in here, and with it the summary that names them."""
    assert tool_writes_with_rows() == set(IMPORTS)


@HUB_DB
@pytest.mark.parametrize("write", IMPORTS)
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_rows_of_a_file_are_named_by_the_name_each_one_gives(write, language):
    second = {**IMPORTS[write], "name": "Guisos QA"}
    if "line" in second:
        second["line"] = 2
    shown = rows_field(write, [IMPORTS[write], second], language)
    assert (shown["kind"], shown["value"], shown.get(NAMED)) == ("list", ["Cucharas QA", "Guisos QA"], True)


@HUB_DB
@pytest.mark.parametrize("write", IMPORTS)
def test_a_name_is_said_as_the_import_keeps_it_and_a_row_without_one_counts_among_the_more(write):
    """The import trims a name and skips a row without one: the card says the trimmed name, and a row with none goes
    among the «more» (never by another of its cells, a SKU or an email nobody asked to check)."""
    rows = [{**IMPORTS[write], "name": "  Guisos QA "}, {**IMPORTS[write], "name": "   "}, {**IMPORTS[write], "name": ""}]
    assert rows_field(write, rows)["value"] == ["Guisos QA", None, None]


@HUB_DB
def test_rows_that_are_no_list_are_said_as_sent():
    """The card is drawn before the write checks what the model sent: rows written as a text stay as they came, and
    the write refuses them."""
    assert rows_field("inventory.category.bulk_create", "Cucharas QA")["value"] == "Cucharas QA"


@HUB_DB
def test_the_rest_of_the_card_stays_as_it_was():
    """The rehearsal of a product import still says «Solo revisar: Sí» beside the rows."""
    card = assistant.cards.card(
        get("inventory.product.bulk_create"), {"rows": [IMPORTS["inventory.product.bulk_create"]], "dry_run": True}, "es", ctx({"*"})
    )
    assert [(field["label"], field["value"]) for field in card["fields"]] == [
        ("Filas del fichero", ["Cucharas QA"]),
        ("Solo revisar", True),
    ]
