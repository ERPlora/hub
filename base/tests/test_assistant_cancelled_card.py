"""What the model hears after the person presses «Cancel» on a card (BASE-F97): that they said no and the card is gone.

«Not confirmed by the person» read as a yes that never arrived («the confirmation did not reach the system») or as a
card still waiting («confirm it on the card you got»), with the card already closed on the screen.
"""

import json

from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.test_services_assistant import answered, call, items

__all__ = ["in_business_a"]

pytestmark = HUB_DB


def heard_after(decision: dict) -> tuple[str, dict]:
    """The outcome of a card to create «Mesa 4» answered with ``decision``, and the error the model hears of it."""
    plan = answered(call("demo.item.create", {"name": "Mesa 4"}), decision=decision)
    assert "Mesa 4" not in items()
    return plan["executed"][0]["outcome"], json.loads(plan["append"][0]["content"])["error"]


def test_a_cancel_is_heard_as_the_persons_no_on_a_card_that_is_closed():
    outcome, error = heard_after({"call_id": "c1", "accepted": False})

    assert (outcome, error["code"]) == ("cancelled", "base.assistant_not_confirmed")
    said = error["message"]
    assert "The person said no on the card" in said
    assert "the card is closed" in said
    assert "nothing was done" in said
    assert "Say it was not done because they said no" in said
    assert "do not tell them to confirm it" in said
    assert not said.startswith("Not confirmed")
