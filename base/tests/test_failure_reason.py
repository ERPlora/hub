"""A write that fails says why on its receipt, in a sentence the person understands (BASE-F97): the one its own screen
would show when its app refuses it; when what failed is the data the assistant sent, which of them, by the name the
card gives each. The reason goes in the language it was said in, so a receipt read in another one is whole without it.

hub#2213: three «Not done, it failed» in a row while building a menu, and the owner never knew why.
"""

import dataclasses
import json

import pytest
from django.utils import translation
from live.context import OperationContext
from live.operations import get, registry
from ninja import Schema
from pydantic import model_validator

from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.test_services_assistant import ASK, LISTED, MANAGER, asked, call, run, turn

__all__ = ["in_business_a"]

pytestmark = HUB_DB


def turn_in(language: str, *calls, decision: dict | None = None) -> dict:
    """``base.assistant.turn`` for a person who reads ``language``, as a request in it runs it."""
    op = get("base.assistant.turn")
    person = OperationContext(scope=A, actor="ana", permissions=MANAGER, language=language)
    data = {"messages": [ASK, asked(*calls)], "pending": list(calls), "decision": decision}
    with translation.override(language):
        return op(person, op.input.model_validate(data)).model_dump(mode="json")


def yes_in(language: str, *calls) -> dict:
    """The turn that draws the card of the first of ``calls``, then the person's yes to it."""
    drawn = turn_in(language, *calls)
    assert drawn["confirm"] is not None
    return turn_in(language, *drawn["pending"], decision={"call_id": drawn["pending"][0]["call_id"], "accepted": True})


def closed_item() -> dict:
    item = run("demo.item.create", name="Mesa 4")
    run("demo.item.update", id=item["id"], status="done")
    return item


@pytest.mark.parametrize(
    ("language", "said"),
    [
        ("es", "Este elemento está cerrado: ábrelo para añadir líneas."),
        ("en", "This item is closed: open it to add lines."),
    ],
)
def test_a_confirmed_write_its_app_refuses_says_why_as_its_screen_does(language, said):
    item = closed_item()
    plan = yes_in(language, call("demo.item.add_line", {"id": item["id"], "text": "Café", "qty": "1"}))
    [row] = plan["executed"]
    assert (row["outcome"], row["code"]) == ("error", "demo.item_done")
    assert row["reason"] == {language: said}
    # The model hears the same refusal, as before.
    assert json.loads(plan["append"][0]["content"])["error"]["message"] == said


@pytest.mark.parametrize(
    ("language", "said"),
    [
        ("es", "El asistente envió datos que no valen: Estado."),
        ("en", "The assistant sent data that does not fit: Status."),
    ],
)
def test_data_the_assistant_sent_that_do_not_fit_are_named_as_the_card_names_them(language, said):
    """The model's own slip (a value off the list): no card, and the receipt names the datum, never its message for
    the model («Input should be 'open' or 'done'»)."""
    plan = turn_in(language, call("demo.item.create", {"name": "Mesa 4", "status": "abierto"}))
    [row] = plan["executed"]
    assert (row["outcome"], row["code"]) == ("error", "invalid_payload")
    assert row["reason"] == {language: said}


def test_each_datum_that_does_not_fit_is_named_once_in_its_order():
    item = run("demo.item.create", name="Mesa 4")
    plan = turn_in("es", call("demo.item.add_line", {"id": item["id"], "text": "", "qty": "0"}))
    assert plan["executed"][0]["reason"] == {"es": "El asistente envió datos que no valen: Texto, Cantidad."}


def test_a_list_is_named_once_however_many_of_its_items_do_not_fit(monkeypatch):
    monkeypatch.setitem(registry, LISTED.name, LISTED)
    plan = turn_in("es", call(LISTED.name, {"starts": ["lunes", "martes"]}))
    assert plan["executed"][0]["reason"] == {"es": "El asistente envió datos que no valen: Starts, Codes."}


class WholeIn(Schema):
    first: int
    last: int

    @model_validator(mode="after")
    def in_order(self):
        if self.last < self.first:
            raise ValueError("last before first")
        return self


WHOLE = dataclasses.replace(LISTED, name="demo.item.reorder", input=WholeIn, output=WholeIn)


def test_what_refuses_the_whole_input_names_no_datum(monkeypatch):
    monkeypatch.setitem(registry, WHOLE.name, WHOLE)
    plan = turn_in("es", call(WHOLE.name, {"first": 3, "last": 1}))
    assert plan["executed"][0]["reason"] == {"es": "El asistente envió datos que no valen."}


def test_the_assistants_slip_is_said_in_the_persons_language_as_its_card_is():
    """The request's language aside: what the Hub itself says goes in the person's (``ctx.language``)."""
    with translation.override("en"):
        plan = turn(call("demo.item.create", {"name": "Mesa 4", "status": "abierto"}))
    assert plan["executed"][0]["reason"] == {"es": "El asistente envió datos que no valen: Estado."}


def test_data_that_are_not_an_object_at_all_say_so_without_naming_any():
    plan = turn_in("es", {"call_id": "c1", "name": "demo__item__create", "arguments": "[1]"})
    [row] = plan["executed"]
    assert (row["outcome"], row["code"]) == ("error", "invalid_payload")
    assert row["reason"] == {"es": "El asistente envió datos que no valen."}


def test_what_ran_or_was_not_tried_carries_no_reason():
    done = yes_in("es", call("demo.item.create", {"name": "Barra"}))
    cancelled = turn_in(
        "es", *turn_in("es", call("demo.item.create", {"name": "Terraza"}))["pending"], decision={"call_id": "c1", "accepted": False}
    )
    not_offered = turn_in("es", call("nothing.at.all", {}))
    assert [row["outcome"] for row in (*done["executed"], *cancelled["executed"], *not_offered["executed"])] == [
        "ok",
        "cancelled",
        "refused",
    ]
    assert [row["reason"] for row in (*done["executed"], *cancelled["executed"], *not_offered["executed"])] == [{}, {}, {}]
