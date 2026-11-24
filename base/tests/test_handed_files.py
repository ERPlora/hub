"""A file a read hands the person in the assistant's chat (the CSV of an export): the turn gives the panel the whole file,
as the screen's export button saves it, and the model hears its name, never its content.

Asked «Sácame la carta entera en un CSV», the model read ``inventory.product.export``, pasted the CSV into its answer and
said it had exported «inventario-productos.csv»: the chat had no file to give. The customers came the same way.
"""

import json

import pytest
from django.utils import translation
from live import assistant as shared
from live.operations import get

from apps.customer.models import Customer
from apps.inventory.models import Product
from base.models import Membership
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.test_services_data import person

__all__ = ["in_business_a"]

pytestmark = HUB_DB

BOM = "﻿"


@pytest.fixture
def owner():
    with translation.override("es"):
        yield person(Membership.Role.OWNER)


@pytest.fixture
def menu():
    Product.objects.create(name="Caña", sku="BEB-01", price=220)
    Product.objects.create(name="Croquetas", sku="TAP-01", price=750)


@pytest.fixture
def lucia():
    Customer.objects.create(name="Lucía Pérez", email="lucia@example.com", phone="600111222")


def asked(name: str, **arguments) -> tuple[list[dict], dict]:
    call = {"call_id": "c1", "name": shared.tool_name(name), "arguments": json.dumps(arguments)}
    function = {"name": call["name"], "arguments": call["arguments"]}
    asking = {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": function}]}
    return [{"role": "user", "content": "Sácame la carta entera en un CSV"}, asking], call


def turn(ctx, name: str, **arguments) -> dict:
    messages, call = asked(name, **arguments)
    op = get("base.assistant.turn")
    return op(ctx, op.input.model_validate({"messages": messages, "pending": [call]})).model_dump(mode="json")


def button(ctx, name: str) -> dict:
    """What the screen's export button receives for the same search: the file it saves."""
    op = get(name)
    return op(ctx, op.input()).model_dump()


def test_the_menu_exported_in_the_chat_is_the_file_of_the_products_button(owner, menu):
    plan = turn(owner, "inventory.product.export")

    [ran] = plan["executed"]
    assert (ran["name"], ran["outcome"]) == ("inventory.product.export", "ok")
    saved = button(owner, "inventory.product.export")
    assert ran["file"] == {"filename": "inventario-productos.csv", "content_type": "text/csv", "content": saved["content"]}
    assert ran["file"]["content"].startswith(BOM)
    assert "Croquetas" in ran["file"]["content"]


def test_the_model_hears_the_files_name_never_its_content_in_this_round_or_the_next(owner, menu):
    plan = turn(owner, "inventory.product.export")

    [result] = plan["append"]
    told = json.loads(result["content"])
    assert {key: value for key, value in told.items() if key != "handed"} == {
        "filename": "inventario-productos.csv",
        "content_type": "text/csv",
    }
    assert told["handed"]
    # The panel sends the whole conversation back with each question, the tool's result with it.
    assert "Croquetas" not in json.dumps(plan["messages"])
    assert "Croquetas" not in json.dumps(plan["append"])


def test_the_customers_exported_in_the_chat_are_the_file_of_the_customers_button(owner, lucia):
    plan = turn(owner, "customer.customer.export")

    [ran] = plan["executed"]
    saved = button(owner, "customer.customer.export")
    # The button saves the CSV with the mark Excel needs to read it as UTF-8 («Lucía», not «LucÃ­a»).
    assert ran["file"] == {"filename": "customers.csv", "content_type": "text/csv", "content": BOM + saved["csv"]}
    assert "lucia@example.com" in ran["file"]["content"]
    told = json.loads(plan["append"][0]["content"])
    assert (told["filename"], told["rows"]) == ("customers.csv", 1)
    assert "lucia@example.com" not in json.dumps(plan["messages"])


def test_a_read_that_hands_no_file_is_told_whole_and_hands_nothing(owner, menu):
    plan = turn(owner, "inventory.product.list")

    [ran] = plan["executed"]
    assert ran["file"] is None
    assert "Croquetas" in plan["append"][0]["content"]


def test_an_export_the_person_may_not_run_hands_no_file(lucia):
    with translation.override("es"):
        employee = person(Membership.Role.EMPLOYEE, username="leo")
        plan = turn(employee, "customer.customer.export")

    [ran] = plan["executed"]
    assert (ran["outcome"], ran["file"]) == ("refused", None)
