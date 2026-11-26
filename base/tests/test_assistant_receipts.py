"""The receipts under an answer of the assistant (BASE-F97) say how each write the person was asked about ended, and
each read: never a write the Hub refused before showing its card. Data its operation would not take or an edit with
nothing to change go back to the model, which hears why and corrects them; the person was never asked, so nothing
failed for them.

hub#2655: «Quita la paella de la carta» deactivated the dish and the receipt added «Not done, it failed: Delete in
Menus and combos», which nobody asked for.
"""

import json

from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.test_services_assistant import ASK, asked, call, run, turn

__all__ = ["in_business_a"]

pytestmark = HUB_DB


def heard(plan: dict) -> list[str]:
    """The code of each tool result the model hears in ``plan``; ``""`` for one that went through."""
    return [json.loads(message["content"]).get("error", {}).get("code", "") for message in plan["append"]]


def test_a_write_whose_data_do_not_fit_leaves_no_receipt_and_the_model_hears_why():
    plan = turn(call("demo.item.create", {"name": "Mesa 4", "status": "abierto"}))
    assert (plan["confirm"], plan["executed"]) == (None, [])
    assert heard(plan) == ["invalid_payload"]


def test_a_write_whose_arguments_are_no_object_leaves_no_receipt():
    plan = turn({"call_id": "c1", "name": "demo__item__create", "arguments": "[1]"})
    assert (plan["confirm"], plan["executed"]) == (None, [])
    assert heard(plan) == ["invalid_payload"]


def test_an_edit_with_nothing_to_change_leaves_no_receipt():
    item = run("demo.item.create", name="Mesa 4")
    plan = turn(call("demo.item.update", {"id": item["id"]}))
    assert (plan["confirm"], plan["executed"]) == (None, [])
    assert heard(plan) == ["base.assistant_nothing_to_change"]


def test_only_the_write_the_person_confirmed_has_a_receipt_beside_a_slip_before_it():
    """The model slips on one write, then asks for the one that does it: the person confirms that one and its receipt
    is the only one."""
    slip = call("demo.item.create", {"name": "Mesa 4", "status": "abierto"}, call_id="c1")
    good = call("demo.item.create", {"name": "Barra"}, call_id="c2")
    drawn = turn(slip, good)
    assert drawn["executed"] == []
    assert drawn["confirm"]["operation"] == "demo.item.create"
    assert heard(drawn) == ["invalid_payload"]
    done = turn(
        *drawn["pending"], decision={"call_id": "c2", "accepted": True}, messages=[ASK, asked(slip, good), *drawn["append"]]
    )
    assert [(row["name"], row["outcome"]) for row in done["executed"]] == [("demo.item.create", "ok")]


def test_a_confirmed_write_that_fails_keeps_its_receipt():
    item = run("demo.item.create", name="Mesa 4")
    run("demo.item.update", id=item["id"], status="done")
    add = call("demo.item.add_line", {"id": item["id"], "text": "Café", "qty": "1"})
    drawn = turn(add)
    done = turn(*drawn["pending"], decision={"call_id": "c1", "accepted": True})
    assert [(row["outcome"], row["code"]) for row in done["executed"]] == [("error", "demo.item_done")]


def test_a_read_that_fails_keeps_its_row():
    plan = turn(call("demo.item.detail", {"id": "0192f0b2-3333-7000-8000-000000000003"}))
    assert [(row["kind"], row["outcome"]) for row in plan["executed"]] == [("query", "error")]


def test_a_write_the_person_declined_keeps_its_receipt():
    drawn = turn(call("demo.item.create", {"name": "Terraza"}))
    declined = turn(*drawn["pending"], decision={"call_id": "c1", "accepted": False})
    assert [row["outcome"] for row in declined["executed"]] == ["cancelled"]
