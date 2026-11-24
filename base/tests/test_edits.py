"""An edit the assistant asks for that changes nothing — it names its record and no datum to change, as
``customer.customer.update`` with its ``id`` alone — shows no card: the person would confirm a change that changes
nothing and read on its receipt that it was done (hub#2324). The model hears that there was nothing to change and goes
on with what was asked, or asks what to change; the receipt says why it was not done (BASE-F97).

It holds for every edit (``<app>.<entity>.update``, where only the data sent change): what names its record is what its
read (``<app>.<entity>.get`` or ``.detail``) takes to find it, and anything else it sends is a change.
"""

import json
import uuid

import pytest
from live.operations import get

from apps.customer.models import Customer
from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import owner_of_a
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, turn_as
from base.tests.test_failure_reason import turn_in
from base.tests.test_services_assistant import call, run, turn

__all__ = ["in_business_a"]

NOTHING_TO_CHANGE = "base.assistant_nothing_to_change"
AN_ID = str(uuid.uuid4())


@pytest.mark.parametrize(
    ("write", "arguments"),
    [
        ("customer.customer.update", {"id": AN_ID}),
        ("customer.customer.update", {"customer": "Lucía QA"}),
        ("inventory.product.update", {"product": "QA cheesecake"}),
        ("table.table.update", {"table": "4", "zone": "Terraza"}),
        ("customer.health.update", {"customer": "Lucía QA"}),
        ("sale.settings.update", {}),
    ],
)
def test_an_edit_that_names_only_its_record_changes_nothing(write, arguments):
    refused = assistant.edits.unchanged(get(write), arguments)
    assert refused is not None
    assert (refused.outcome, refused.code) == ("error", NOTHING_TO_CHANGE)
    assert json.loads(refused.content)["error"]["code"] == NOTHING_TO_CHANGE


@pytest.mark.parametrize(
    ("write", "arguments"),
    [
        ("customer.customer.update", {"id": AN_ID, "email": "lucia@example.com"}),
        ("inventory.product.update", {"product": "QA cheesecake", "price": 600}),
        # A datum that names another record of its own kind (the parent category) is a change, not the record.
        ("service.category.update", {"id": AN_ID, "parent_id": AN_ID}),
        ("table.table.update", {"id": AN_ID, "move_to_zone_id": AN_ID}),
        ("sale.settings.update", {"allow_cash": False}),
        # Not edits: a write that only names records still does something.
        ("customer.order.link", {"order_id": AN_ID, "customer": "Lucía QA"}),
        ("customer.customer.delete", {"id": AN_ID}),
    ],
)
def test_an_edit_that_sends_something_to_change_or_another_write_goes_on(write, arguments):
    assert assistant.edits.unchanged(get(write), arguments) is None


@HUB_DB
def test_an_edit_with_nothing_to_change_shows_no_card_and_changes_nothing():
    item = run("demo.item.create", name="Mesa 4")
    for named in ({"id": item["id"]}, {"called": "Mesa 4"}):
        plan = turn(call("demo.item.update", named))
        no_card_but_the_model_hears(plan, NOTHING_TO_CHANGE)
    assert run("demo.item.detail", id=item["id"])["updated_at"] == item["updated_at"]


@HUB_DB
def test_an_edit_with_something_to_change_still_shows_its_card():
    item = run("demo.item.create", name="Mesa 4")
    plan = turn(call("demo.item.update", {"id": item["id"], "note": "Junto a la ventana"}))
    assert plan["confirm"]["operation"] == "demo.item.update"
    assert plan["executed"] == []


@HUB_DB
@pytest.mark.parametrize(
    ("language", "said"),
    [("es", "El asistente no dijo qué cambiar."), ("en", "The assistant did not say what to change.")],
)
def test_the_receipt_says_the_assistant_did_not_say_what_to_change(language, said):
    item = run("demo.item.create", name="Mesa 4")
    [row] = turn_in(language, call("demo.item.update", {"id": item["id"]}))["executed"]
    assert (row["outcome"], row["code"], row["reason"]) == ("error", NOTHING_TO_CHANGE, {language: said})


@HUB_DB
def test_the_customer_card_of_the_report_is_not_shown_and_stays_as_it_was(make_user):
    """The owner's «La cuenta de la mesa 4 es de Lucía QA, ponla a su nombre.»: the model asked to change Lucía's card
    with nothing to change."""
    owner = owner_of_a(make_user, "es")
    lucia = Customer.objects.create(name="Lucía QA")
    plan = turn_as(owner, call("customer.customer.update", {"id": str(lucia.id)}))
    no_card_but_the_model_hears(plan, NOTHING_TO_CHANGE)
    assert Customer.objects.get(id=lucia.id).updated_at == lucia.updated_at
