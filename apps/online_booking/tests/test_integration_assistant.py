"""The assistant's confirmation card names each datum of a write of Online booking by a name of the app's own
(FIX-HUB-ONLINE_BOOKING-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title
pydantic makes up from the field («Slot Interval», «Allow Customer Cancellation»), nor by a word another app's catalog
happens to lend («Number» → «Número», from Customers'). The card is base's (``base.assistant.card``); the names are
online_booking's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog,
as its screens (the bookings list, the booking page's settings and its preview) say them."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

APP = Path(apps.get_app_config("online_booking").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["online_booking"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["online_booking"]

#: The writes of Online booking the assistant calls, by name (the public page's own included: they are tools too).
TOOLS = sorted(
    name
    for name, op in registry.items()
    if op.app_label == "online_booking" and op.kind == "command" and assistant.is_tool(op)
)

#: The booking page's rules (the diary's) as its settings screen lists them.
RULES = (
    "min_booking_notice",
    "max_advance_booking",
    "slot_interval",
    "auto_confirm_online",
    "allow_customer_cancellation",
    "cancellation_notice_hours",
)

#: The writes that find a booking by its number or by its customer and day, as the bookings list does.
BY_BOOKING = (
    "online_booking.booking.cancel",
    "online_booking.booking.complete",
    "online_booking.booking.confirm",
    "online_booking.booking.delete",
    "online_booking.booking.no_show",
)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def named_by_online_booking(op, name: str, title: str | None) -> bool:
    """Whether online_booking itself names the datum ``name`` of ``op``: by its schema's own title, by the
    ``verbose_name`` of one of its models, or by its own catalog. A title pydantic made up that another app's catalog
    happens to translate is not a name of Online booking: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("online_booking", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_online_booking_reaches_a_spanish_card_by_its_technical_name():
    """Every write of online_booking the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up. By where the name comes from, not by the word."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 9  # positive control: the registry has online_booking's writes
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_online_booking(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


@pytest.mark.parametrize("rule", RULES)
def test_the_card_names_each_booking_rule_as_the_settings_screen(rule):
    update = get("online_booking.settings.update")
    assert labels(assistant.card(update, {rule: 1}, "es")) == [SCREENS["settings"]["fields"][rule]]
    assert labels(assistant.card(update, {rule: 1}, "en")) == [SCREENS_EN["settings"]["fields"][rule]]


def test_the_card_names_a_booking_by_its_number_or_its_customer_as_the_bookings_list():
    """Its day (``date``) the card's screen names itself, as every app's."""
    arguments = {"number": "APT-20300305-0001", "customer": "Ana"}
    columns = [SCREENS["bookings"]["columns"][key] for key in ("number", "customer")]
    columns_en = [SCREENS_EN["bookings"]["columns"][key] for key in ("number", "customer")]
    for name in BY_BOOKING:
        assert labels(assistant.card(get(name), arguments, "es")) == columns
        assert labels(assistant.card(get(name), arguments, "en")) == columns_en


def test_the_card_names_a_booking_from_the_page_as_the_page_asks_for_it():
    """The customer's booking, with the words of the booking page (its preview): its services and its professional;
    when, by its day and time. Her name, mobile, email and note the card's screen names itself, as every app's."""
    book = get("online_booking.public.book")
    arguments = {"service_ids": ["x"], "staff_id": "x", "start": "2030-03-05 10:00"}
    page, page_en = SCREENS["preview"], SCREENS_EN["preview"]
    assert labels(assistant.card(book, arguments, "es")) == [page["services"], page["professional"], "Día y hora"]
    assert labels(assistant.card(book, arguments, "en")) == [page_en["services"], page_en["professional"], "Day and time"]
    assert {"name", "phone", "email", "notes"} <= named_by_the_screen()


def test_the_card_names_the_token_by_the_customers_personal_link():
    cancel = get("online_booking.public.cancel")
    assert labels(assistant.card(cancel, {"token": "x"}, "es")) == [SCREENS["preview"]["link"]]
    assert labels(assistant.card(cancel, {"token": "x"}, "en")) == [SCREENS_EN["preview"]["link"]]
