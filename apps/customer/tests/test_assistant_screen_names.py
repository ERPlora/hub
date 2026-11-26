"""What the assistant's model reads of a customer's stage and source: beside their codes, the names her card shows, in
the person's language.

Created in Spanish, Lucía's card says «Contacto» and «En el local»; the model only read «lead» and «walk_in», and wrote
them as they came: «Ha quedado con la etapa «lead» y origen «walk-in»».
"""

import json
from pathlib import Path

from live import assistant as shared
from live.operations import get

from apps.customer.tests.conftest import HUB_DB, ctx_for, in_business_a

__all__ = ["in_business_a"]
pytestmark = HUB_DB

#: What the customer's card on the screen says, in Spanish.
SCREEN = json.loads((Path(__file__).parents[1] / "frontend" / "locale" / "es.json").read_text())["customer"]


def told(operation: str, arguments: dict, *, yes: bool = False) -> dict:
    """What the model reads of the tool ``operation`` run in a turn of an employee in Spanish, as the chat runs it; a
    write, once the employee says yes to its card (``yes``)."""
    call = {"call_id": "c1", "name": shared.tool_name(operation), "arguments": json.dumps(arguments)}
    asked = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}],
    }
    messages = [{"role": "user", "content": "Da de alta a una clienta nueva."}, asked]
    turn = get("base.assistant.turn")

    def answer(pending: list, decision: dict | None) -> dict:
        data = turn.input.model_validate({"messages": messages, "pending": pending, "decision": decision})
        return turn(ctx_for("hub_employee", language="es"), data).model_dump(mode="json")

    plan = answer([call], None)
    if yes:
        plan = answer(plan["pending"], {"call_id": "c1", "accepted": True})
    [result] = plan["append"]
    return json.loads(result["content"])


def test_a_new_customer_reaches_the_model_with_her_stage_and_source_as_her_card_names_them():
    created = told("customer.customer.create", {"name": "Lucía Gómez QA"}, yes=True)
    assert (created["lifecycle_stage"], created["source"]) == ("lead", "walk_in")
    names = created["screen_names"]
    assert names["lifecycle_stage"] == {"lead": SCREEN["stage"]["lead"]}
    assert names["source"] == {"walk_in": SCREEN["source"]["walk_in"]}


def test_a_list_of_customers_names_each_stage_once_however_many_rows_have_it():
    for name in ("Ana", "Bea", "Carla"):
        told("customer.customer.create", {"name": name}, yes=True)
    rows = told("customer.customer.list", {})
    assert [row["lifecycle_stage"] for row in rows["rows"]] == ["lead", "lead", "lead"]
    assert rows["screen_names"]["rows.lifecycle_stage"] == {"lead": SCREEN["stage"]["lead"]}
