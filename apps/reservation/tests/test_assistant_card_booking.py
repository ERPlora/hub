"""The card of booking a table from the assistant (RESERVATION-F06): its one line says for whom, the day and the time
(«Crear en Reservas: Ana García · 15 oct 2026 · 21:00»): the customer by the name of her card, or the guest's name
when there is no card, and that name only once."""

import pytest
from live.operations import get

from base import assistant

from .conftest import HUB_DB, TOMORROW, ctx_for, make_customer

CREATE = "reservation.reservation.create"

#: Thursday 15 October 2026 at 21:00, as each language writes a day and a time on the card (CLDR: a narrow no-break
#: space before «PM»).
DAY = {"es": "15 oct 2026", "en": "Oct 15, 2026"}
HOUR = {"es": "21:00", "en": "9:00 PM"}
BOOKING = {"date": TOMORROW.isoformat(), "time": "21:00", "party_size": 4}


def card_line(arguments: dict, language: str) -> str:
    """The card's line as the chat writes a normal write (``cardLine`` of @erplora/ui): its first three data, the
    empty ones left out."""
    card = assistant.cards.card(get(CREATE), arguments, language, ctx=ctx_for(language=language))
    shown = [field["value"] for field in card["fields"] if field["kind"] != "empty"]
    return " · ".join(str(value) for value in shown[:3])


def card_values(arguments: dict, language: str) -> list:
    card = assistant.cards.card(get(CREATE), arguments, language, ctx=ctx_for(language=language))
    return [field["value"] for field in card["fields"]]


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_customer_said_by_her_name_with_the_same_guest_name_and_her_phone_is_named_once_before_the_day_and_hour(
    language,
):
    """hub#2169: «Ana García · Ana García · 15 oct 2026» repeated the name and left the time out."""
    make_customer("Ana García", phone="+34600000001")
    arguments = {**BOOKING, "customer": "Ana García", "guest_name": "Ana García", "guest_phone": "600 000 001"}
    assert card_line(arguments, language) == f"Ana García · {DAY[language]} · {HOUR[language]}"
    assert card_values(arguments, language).count("Ana García") == 1


@HUB_DB
def test_the_guest_name_written_without_accents_or_capitals_is_not_said_again():
    make_customer("Ana García", phone="+34600000001")
    arguments = {**BOOKING, "customer": "Ana García", "guest_name": "ana garcia"}
    assert card_line(arguments, "es") == "Ana García · 15 oct 2026 · 21:00"
    assert "ana garcia" not in card_values(arguments, "es")


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_customer_said_by_her_phone_is_named_by_her_card(language):
    make_customer("Ana García", phone="+34600000001")
    arguments = {**BOOKING, "customer": "600 000 001"}
    assert card_line(arguments, language) == f"Ana García · {DAY[language]} · {HOUR[language]}"


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_customer_by_her_card_id_is_named_by_her_card(language):
    ana = make_customer("Ana García", phone="+34600000001")
    arguments = {**BOOKING, "customer_id": str(ana.id), "guest_phone": "600 000 001"}
    assert card_line(arguments, language) == f"Ana García · {DAY[language]} · {HOUR[language]}"


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_guest_without_a_card_is_named_by_the_name_said_before_her_phone(language):
    arguments = {**BOOKING, "guest_name": "Lucía Pérez", "guest_phone": "600 000 002"}
    assert card_line(arguments, language) == f"Lucía Pérez · {DAY[language]} · {HOUR[language]}"


@HUB_DB
def test_a_guest_name_other_than_her_cards_is_still_on_the_card_after_the_day_and_hour():
    """The reservation is kept under the name typed («Ana»), linked to the card «Ana García»: both are said."""
    ana = make_customer("Ana García", phone="+34600000001")
    arguments = {**BOOKING, "customer_id": str(ana.id), "guest_name": "Ana"}
    assert card_line(arguments, "es") == "Ana García · 15 oct 2026 · 21:00"
    assert "Ana" in card_values(arguments, "es")
