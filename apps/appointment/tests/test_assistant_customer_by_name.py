"""A customer's appointments asked to the assistant by her name as a person says it (hub#2329).

The card is «Lucía Fernández QA»; the person asking says «Lucía Fernández», «Fernández», «Lucía» or, on an English
keyboard, «Lucia Fernandez». Each one is her, as the Customers list finds her by any of those words. When two cards
fit, the answer names them for the person to choose, as the assistant does with two members of the team."""

import json

import pytest
from django.utils import translation
from live.operations import get

from base import assistant

from .conftest import HUB_DB, MONDAY, at, ctx_for, make_appointment, make_customer, make_member, make_service

pytestmark = HUB_DB

VISITS = "appointment.appointment.list_for_customer"


@pytest.fixture
def lucia():
    """«Lucía Fernández QA» with a cut on Monday, and another customer with her own appointment the same day."""
    carlos, cut = make_member("Carlos", "Gil"), make_service("Corte de mujer")
    card = make_customer("Lucía Fernández QA", phone="+34600222333")
    visit = make_appointment(card, carlos, [cut], at(MONDAY, "17:00"))
    make_appointment(make_customer("Carmen Ruiz", phone="+34600444555"), carlos, [cut], at(MONDAY, "18:00"))
    return card, visit


def asked(reference: str, language: str = "es"):
    """What the assistant gets back when it asks for the appointments of ``reference``, as the business's owner, in
    the request of a person who speaks ``language``."""
    with translation.override(language):
        return assistant.tools.run(
            ctx_for("hub_owner", language=language), get(VISITS), json.dumps({"customer": reference})
        )


@pytest.mark.parametrize("reference", ["Lucía Fernández", "Fernández", "Lucía", "Lucia Fernandez", "lucía fernández qa"])
def test_her_appointments_come_by_her_name_as_a_person_says_it(lucia, reference):
    card, visit = lucia
    outcome = asked(reference)
    assert outcome.outcome == "ok", outcome.content
    assert [row["id"] for row in json.loads(outcome.content)["rows"]] == [str(visit.id)]


def refusal(outcome) -> tuple[str, str]:
    error = json.loads(outcome.content)["error"]
    return error["code"], error["message"]


def test_two_customers_that_fit_are_named_for_the_person_to_choose_in_her_language(lucia):
    make_customer("Lucía Gómez", phone="+34600666777")
    spanish, english = asked("Lucía", "es"), asked("Lucía", "en")
    assert spanish.outcome == english.outcome == "error"
    (code, said), (_, told) = refusal(spanish), refusal(english)
    assert code == "customer.customer_ambiguous"
    for message in (said, told):
        assert "Lucía Fernández QA" in message and "Lucía Gómez" in message
        assert "Carmen Ruiz" not in message
    assert said != told


def test_a_name_no_card_holds_is_still_no_customer(lucia):
    outcome = asked("Fernanda Ortiz")
    assert (outcome.outcome, outcome.code) == ("error", "customer.customer_unavailable"), outcome.content
