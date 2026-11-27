"""Booking from the assistant for somebody who calls giving only her phone (RESERVATION-F06): «Me llama la del
600 000 001 para mañana a las dos, son cuatro». The card says whom it is for by the card that number is on, then the
day and the time, and the yes books it under that card. With no card for that number, no card is drawn: the model
hears whom the reservation is for is missing, to ask for the guest's name, and nothing is written down."""

import json

import pytest

from apps.customer.models import Customer
from apps.reservation.models import Reservation
from base.tests import card_turn

from .conftest import HUB_DB, TOMORROW, ctx_for, make_customer, open_week

pytestmark = HUB_DB

CREATE = "reservation.reservation.create"
SAID = "Me llama la del 600 000 001 para mañana a las dos, son cuatro"
#: Thursday 15 October 2026 at 14:00, as each language writes them on the card (CLDR: a narrow no-break space before
#: «PM»).
DAY = {"es": "15 oct 2026", "en": "Oct 15, 2026"}
HOUR = {"es": "14:00", "en": "2:00 PM"}
BY_PHONE = {"guest_phone": "600 000 001", "date": TOMORROW.isoformat(), "time": "14:00", "party_size": 4, "source": "phone"}
YES = {"call_id": "c1", "accepted": True}


def asked(arguments: dict, language: str = "es", decision: dict | None = None, pending: dict | None = None) -> dict:
    """The turn of an employee whose model asked to book with ``arguments``."""
    ctx = ctx_for("hub_employee", language=language)
    return card_turn.turn(ctx, pending or card_turn.call(CREATE, arguments), said=SAID, decision=decision)


def heard(plan: dict) -> dict:
    """What the model hears of the write it asked for."""
    return json.loads(plan["append"][-1]["content"])


@pytest.mark.parametrize("language", ["es", "en"])
def test_a_booking_said_only_by_the_phone_of_a_card_names_her_first_on_the_card(language):
    make_customer("Lucía Gómez", phone="+34600000001")
    card = asked(BY_PHONE, language)["confirm"]
    assert [field["value"] for field in card["fields"]][:3] == ["Lucía Gómez", DAY[language], HOUR[language]]
    assert "600 000 001" in [field["value"] for field in card["fields"]][3:]


def test_the_yes_to_it_books_it_under_her_card():
    open_week()
    lucia = make_customer("Lucía Gómez", phone="+34600000001")
    drawn = asked(BY_PHONE)
    plan = asked(BY_PHONE, decision=YES, pending=drawn["pending"][0])
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("ok", "")]
    booked = Reservation.objects.get()
    assert (booked.customer_id, booked.guest_name, booked.guest_phone) == (lucia.id, "Lucía Gómez", "+34600000001")


def test_with_no_card_for_that_phone_the_model_hears_whom_it_is_for_is_missing_before_any_card():
    plan = asked(BY_PHONE)
    assert plan["confirm"] is None
    assert (heard(plan)["error"]["code"], set(heard(plan)["error"]["fields"])) == ("reservation.no_guest", {"guest_name"})
    assert plan["executed"] == []
    assert (Customer.objects.count(), Reservation.objects.count()) == (0, 0)


def test_a_customer_said_by_a_phone_no_card_has_is_refused_before_any_card():
    plan = asked({**BY_PHONE, "guest_phone": "", "customer": "600 000 001"})
    assert plan["confirm"] is None
    assert heard(plan)["error"]["code"] == "customer.customer_unavailable"
    assert plan["executed"] == []
