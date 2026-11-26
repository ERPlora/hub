"""What the assistant's model reads of a customer's stage and source: beside their codes, the names her card shows, in
the person's language.

Created in Spanish, Lucía's card says «Contacto» and «En el local»; the model only read «lead» and «walk_in», and wrote
them as they came: «Ha quedado con la etapa «lead» y origen «walk-in»».
"""

import json
from pathlib import Path

from apps.customer.tests.conftest import HUB_DB, in_business_a, told_in_a_turn

__all__ = ["in_business_a"]
pytestmark = HUB_DB

#: What the customer's card on the screen says, in Spanish.
SCREEN = json.loads((Path(__file__).parents[1] / "frontend" / "locale" / "es.json").read_text())["customer"]


def told(operation: str, arguments: dict, *, yes: bool = False) -> dict:
    """What the model reads of the tool ``operation`` run in a turn of an employee in Spanish (``told_in_a_turn``)."""
    return told_in_a_turn(operation, arguments, ask="Da de alta a una clienta nueva.", role="hub_employee", yes=yes)


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
