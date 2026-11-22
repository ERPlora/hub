"""The card of adding a product to an open check (``sale.order.add_line``), as the assistant shows it before the yes:
the product it will add, found as the write finds it, and the check by where it is, in the person's language.

The catalog has «Espresso» and «White coffee», and no product called «Coffee»: «two coffees» adds White coffee, the
only name that contains the word, and the card says so. Words that fit several products, or none, are said as they
were said, and the write adds none of them.
"""

import pytest
from live.context import OperationContext, system_context
from live.errors import Conflict
from live.operations import get, registry

from apps.sale.models import OrderLine
from apps.sale.tests.conftest import HUB_DB, A, ctx_for, run
from base import assistant

pytestmark = HUB_DB

ADD = "sale.order.add_line"


def card_values(arguments: dict, language: str = "en", ctx=None) -> list:
    """The values of the card's line, in the order the person reads them («2 · White coffee · 4 (Dining room)»)."""
    card = assistant.cards.card(get(ADD), arguments, language, ctx or ctx_for(language=language))
    return [field["value"] for field in card["fields"]]


def said(arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.cards.card(get(ADD), arguments, language, ctx or ctx_for(language=language))
    return {field["name"]: field["value"] for field in card["fields"]}


@pytest.fixture
def coffees(product):
    product("Espresso", "ESP", 130, "restaurant.drink")
    return product("White coffee", "WHC", 180, "restaurant.drink")


@pytest.fixture
def check(coffees):
    return run("sale.order.open", {"label": "Bar 2"})


@pytest.fixture
def dining_room(db):
    run("table.zone.create", {"name": "Dining room"}, system_context(A))
    run("table.table.create", {"zone": "Dining room", "number": "4"}, system_context(A))


def seated_in_spanish(table: str = "4", **where) -> str:
    """The check of ``table``, seated on screen by somebody who works in Spanish: Sales titles it «Mesa 4»."""
    seated = run("table.session.open", {"table": table, **where}, ctx_for(language="es"))
    assert run("sale.order.get", {"order_id": str(seated.order_id)}).label == f"Mesa {table}"
    return str(seated.order_id)


# ── The product: the one the write will add ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("language", ["en", "es"])
def test_a_product_said_in_words_is_the_one_the_write_finds(check, language):
    arguments = {"order_id": str(check.id), "product": "coffee", "quantity": "2"}
    assert said(arguments, language)["product"] == "White coffee"


def test_the_product_the_card_shows_is_the_one_added(check):
    arguments = {"order_id": str(check.id), "product": "coffee", "quantity": "2"}
    shown = said(arguments)["product"]
    run(ADD, arguments)
    assert [line.name for line in OrderLine.objects.filter(order_id=check.id)] == [shown]


def test_words_that_fit_several_products_are_said_as_said_and_add_none(check, product):
    product("Iced coffee", "ICE", 250, "restaurant.drink")
    arguments = {"order_id": str(check.id), "product": "coffee", "quantity": "2"}
    assert said(arguments)["product"] == "coffee"
    with pytest.raises(Conflict) as refused:
        run(ADD, arguments)
    assert refused.value.code == "inventory.product_ambiguous"
    assert not OrderLine.objects.filter(order_id=check.id).exists()


def test_words_that_fit_no_product_are_said_as_said(check):
    assert said({"order_id": str(check.id), "product": "tea"})["product"] == "tea"


def test_a_product_named_by_its_id_leaves_the_words_unread(check, coffees):
    shown = said({"order_id": str(check.id), "product_id": str(coffees.id), "product": "espresso"})
    assert (shown["product_id"], "product" in shown) == ("White coffee", False)


def test_a_better_match_created_before_the_yes_changes_the_card(check, product):
    arguments = {"order_id": str(check.id), "product": "coffee"}
    before = said(arguments)["product"]
    product("Coffee", "COF", 150, "restaurant.drink")
    assert (before, said(arguments)["product"]) == ("White coffee", "Coffee")


# ── The check: by where it is, in the person's language ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_card_says_the_product_and_the_table_of_the_check(coffees, dining_room, language):
    order_id = seated_in_spanish()
    arguments = {"order_id": order_id, "product": "coffee", "quantity": "2"}
    assert card_values(arguments, language) == ["2", "White coffee", "4 (Dining room)"]


@pytest.mark.parametrize(("language", "where"), [("en", "4 (no zone)"), ("es", "4 (sin zona)")])
def test_a_table_without_a_zone_is_said_in_the_persons_language(coffees, language, where):
    run("table.table.create", {"number": "4"}, system_context(A))
    order_id = seated_in_spanish()
    assert said({"order_id": order_id, "product": "coffee"}, language)["order_id"] == where


def test_a_check_taken_off_its_table_is_said_by_its_title(coffees, dining_room):
    order_id = seated_in_spanish()
    (session,) = run("table.session.by_order", {"order_id": order_id}).rows
    run("table.session.park", {"id": str(session.id)})
    assert said({"order_id": order_id, "product": "coffee"})["order_id"] == "Mesa 4"


def test_without_tables_a_check_is_said_by_its_title(coffees, dining_room, monkeypatch):
    order_id = seated_in_spanish()
    for name in [name for name in registry if name.startswith("table.")]:
        monkeypatch.delitem(registry, name)
    assert said({"order_id": order_id, "product": "coffee"})["order_id"] == "Mesa 4"


def test_whoever_may_not_see_the_tables_reads_the_check_by_its_title(coffees, dining_room):
    order_id = seated_in_spanish()
    everything = ctx_for()
    cashier = OperationContext(
        scope=A,
        actor="cashier",
        permissions=frozenset(p for p in everything.permissions if not p.startswith("table.")),
        language="en",
    )
    assert said({"order_id": order_id, "product": "coffee"}, ctx=cashier)["order_id"] == "Mesa 4"
