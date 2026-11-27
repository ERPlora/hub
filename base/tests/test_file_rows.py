"""The card of a write that creates several records at once through the assistant — an import from a file, or people
and services the person dictates —: the rows it will create, each by the name its row gives, never «File rows: 2
items» — the person can only check what they are told (hub#2241, hub#2619)."""

import pytest
from live.assistant import NAMED, resolved
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


#: The writes that create a record of each row of a list the person dictates: the list, two rows as the model sends
#: them (with what else each one says: a yes or no, an email, a price) and the name each row gives — a person by their
#: first name and last name together, as the directory writes them.
BATCHES = {
    "staff.member.bulk_create": (
        "members",
        [
            {"first_name": "Carla", "last_name": "Ruiz QA", "is_bookable": True},
            {"first_name": "Diego", "last_name": "Martín QA", "email": "diego@example.com"},
        ],
        ["Carla Ruiz QA", "Diego Martín QA"],
    ),
    "service.service.bulk_create": (
        "services",
        [{"name": "Corte QA", "price": 1500, "duration_minutes": 30}, {"name": "Tinte QA", "is_bookable": False}],
        ["Corte QA", "Tinte QA"],
    ),
}

#: The lists whose rows give a name that their own app's card says otherwise: each special day by its date and its name.
SAID_BY_THEIR_APP = {"schedule.special_day.bulk_create:special_days"}


def named_row_lists() -> set[str]:
    """The lists of the writes the assistant offers whose every row must give a name: a ``name``, or a first name and a
    last name."""
    found = set()
    for op in registry.values():
        if op.kind != "command" or not assistant.tools.is_tool(op):
            continue
        schema = op.input.model_json_schema()
        defs = schema.get("$defs", {})
        for datum, prop in schema.get("properties", {}).items():
            required = set(resolved(resolved(prop, defs).get("items", {}), defs).get("required", ()))
            if "name" in required or {"first_name", "last_name"} <= required:
                found.add(f"{op.name}:{datum}")
    return found


def test_every_write_of_records_the_person_names_row_by_row_says_each_one():
    """A new write that creates several named records at once comes in here, and with it the summary that names them."""
    assert named_row_lists() == {f"{write}:{datum}" for write, (datum, _, _) in BATCHES.items()} | SAID_BY_THEIR_APP


def batch_field(write: str, rows: list, language: str = "es") -> dict:
    datum = BATCHES[write][0]
    card = assistant.cards.card(get(write), {datum: rows}, language, ctx({"*"}, language=language))
    return next(field for field in card["fields"] if field["name"] == datum)


@HUB_DB
@pytest.mark.parametrize("write", BATCHES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_rows_a_person_dictates_are_named_by_the_name_each_one_gives(write, language):
    """Whatever else a row says (a yes or no, an email, a price), the card says who or what it creates."""
    _, rows, names = BATCHES[write]
    shown = batch_field(write, rows, language)
    assert (shown["kind"], shown["value"], shown.get(NAMED)) == ("list", names, True)


@HUB_DB
def test_a_person_is_said_by_both_names_trimmed_and_a_row_missing_one_counts_among_the_more():
    """The write trims each name and skips a row without its first name or its last name (``name_required``): the card
    says the trimmed names, and a row missing either goes among the «more», never by the half it has."""
    rows = [
        {"first_name": "  Elena ", "last_name": " Sanz QA  "},
        {"first_name": "Diego", "last_name": "   "},
        {"first_name": "", "last_name": "Martín QA"},
        {"last_name": "Gil QA"},
    ]
    assert batch_field("staff.member.bulk_create", rows)["value"] == ["Elena Sanz QA", None, None, None]


@HUB_DB
def test_rows_a_person_dictates_that_are_no_list_are_said_as_sent():
    """The card is drawn before the write checks what the model sent: people written as a text stay as they came."""
    assert batch_field("staff.member.bulk_create", "Carla Ruiz QA")["value"] == "Carla Ruiz QA"
