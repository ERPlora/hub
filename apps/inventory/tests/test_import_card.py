"""The card of an import of products or categories from a file through the assistant: its rows by their names and,
once each and by the names the Taxes screens give them, the tax categories those rows take — the fiscal text of a
file is what the person most needs to check before the yes."""

import pytest
from live.assistant import NAMED
from live.operations import get

from apps.tax.tests.conftest import HUB_DB, ctx_for
from base import assistant

IMPORTS = ("inventory.category.bulk_create", "inventory.product.bulk_create")
LABELS = {"es": "Categoría fiscal", "en": "Tax category"}
GENERIC = {"es": "Producto — general", "en": "Product — generic"}


def fields(write: str, rows: list, language: str) -> dict:
    card = assistant.cards.card(get(write), {"rows": rows}, language, ctx_for(role="hub_owner", language=language))
    return {field["name"]: field for field in card["fields"]}


@HUB_DB
@pytest.mark.parametrize("write", IMPORTS)
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_tax_categories_of_the_rows_are_said_once_each_by_their_names(write, language):
    rows = [
        {"line": 1, "name": "Cucharas QA", "tax_category_key": "product.generic"},
        {"line": 2, "name": "Guisos QA", "tax_category_key": "product.generic"},
    ]
    shown = fields(write, rows, language)
    assert shown["rows"]["value"] == ["Cucharas QA", "Guisos QA"]
    category = shown["tax_category_key"]
    assert (category["label"], category["kind"], category["value"], category.get(NAMED)) == (
        LABELS[language],
        "list",
        [GENERIC[language]],
        True,
    )


@HUB_DB
@pytest.mark.parametrize("write", IMPORTS)
def test_rows_without_a_tax_category_add_no_line(write):
    """The import asks for the fiscal text that is missing (INVENTORY-F09, step 5): the card says nothing of it."""
    shown = fields(write, [{"line": 1, "name": "Cucharas QA", "tax_category_key": ""}, {"line": 2, "name": "Guisos QA"}], "es")
    assert list(shown) == ["rows"]
