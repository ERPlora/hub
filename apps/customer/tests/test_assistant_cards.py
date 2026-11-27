"""hub#2288: the card of a write of Customers says what the person wrote, never «2 items»: the options of a select field
one by one («Options: Terrace, Inside») and each custom field a card is given by its name and its value, as that field's
card shows it — a yes or no in the person's language, a day as the card writes one, a field left empty by a dash
(CUSTOMER-F29, CUSTOMER-F04).
"""

import pytest
from live.assistant import NAMED

from apps.customer.models import Customer, CustomField

from .conftest import HUB_DB, ctx_for
from .test_assistant_card_records import fields_of

UPDATE = "customer.customer.update"


def values_of(field_type: str, *values: str, language: str = "en", ctx=None, **more) -> dict:
    """The card of setting ``values`` on a card's custom field of ``field_type``, one line each."""
    field = CustomField.objects.create(name="VIP", field_type=field_type, **more)
    card = Customer.objects.create(name="Lucía QA")
    lines = [{"field_id": str(field.id), "value": value} for value in values]
    return fields_of(UPDATE, {"id": str(card.id), "field_values": lines}, language, ctx)["field_values"]


# ── The options of a select field ─────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_options_of_a_new_select_field_are_said_one_by_one(language):
    """The issue's card said «Preferencia de mesa · Selección · 2 elementos»."""
    arguments = {"name": "Preferencia de mesa", "field_type": "select", "options": ["Terraza", "Dentro"]}
    options = fields_of("customer.field.create", arguments, language)["options"]
    assert (options["value"], options.get(NAMED)) == (["Terraza", "Dentro"], True)


@HUB_DB
def test_the_new_options_of_a_field_are_said_one_by_one_too():
    field = CustomField.objects.create(name="Preferencia de mesa", field_type="select", options=["Terraza"])
    arguments = {"id": str(field.id), "options": ["Terraza", "Dentro", "Barra"]}
    options = fields_of("customer.field.update", arguments)["options"]
    assert (options["value"], options.get(NAMED)) == (["Terraza", "Dentro", "Barra"], True)


# ── The value of a custom field ───────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_custom_field_is_said_by_its_name_and_the_value_written(language):
    """The issue's card said «Lucía QA · 1 elemento»: now «Lucía QA · Campos personalizados: VIP · Terraza»."""
    said = values_of("select", "Terraza", language=language, options=["Terraza", "Dentro"])
    assert (said["value"], said.get(NAMED)) == ([{"field_id": "VIP", "value": "Terraza"}], True)


@HUB_DB
@pytest.mark.parametrize(("language", "yes", "no"), [("en", "Yes", "No"), ("es", "Sí", "No")])
def test_a_yes_or_no_field_says_yes_or_no_in_the_persons_language(language, yes, no):
    """A yes or no field takes «true» or «1», «false» or «0»: never said as that code, in English."""
    said = values_of("boolean", "true", "0", "FALSE", "1", language=language)
    assert [line["value"] for line in said["value"]] == [yes, no, no, yes]
    assert said.get(NAMED) is True


@HUB_DB
@pytest.mark.parametrize(("language", "day"), [("en", "Jan 2, 2027"), ("es", "2 ene 2027")])
def test_a_date_field_says_its_day_as_the_card_writes_one(language, day):
    said = values_of("date", "2027-01-02", language=language)
    assert [line["value"] for line in said["value"]] == [day]


@HUB_DB
def test_a_field_left_empty_is_said_by_a_dash_as_the_card_says_an_empty_datum():
    """Clearing a field said only «VIP», which reads as setting it."""
    said = values_of("boolean", "")
    assert (said["value"], said.get(NAMED)) == ([{"field_id": "VIP", "value": "—"}], True)


@HUB_DB
@pytest.mark.parametrize(("field_type", "sent"), [("boolean", "maybe"), ("date", "02/01/2027"), ("text", "true")])
def test_a_value_the_write_refuses_or_keeps_as_text_is_said_as_written(field_type, sent):
    """The write refuses a yes or no that is none and a day that is none; a text field keeps «true» as it was written."""
    said = values_of(field_type, sent)
    assert [line["value"] for line in said["value"]] == [sent]


@HUB_DB
def test_a_field_the_person_may_not_read_leaves_the_list_said_by_how_many():
    """Without the field's name the value alone would read as anything: the card counts the line, as it did."""
    allowed = ctx_for()
    blind = ctx_for(permissions=set(allowed.permissions) - {"customer.view"})
    said = values_of("boolean", "true", ctx=blind)
    assert said.get(NAMED) is None
    assert said["value"] == [{"value": "true"}]


@HUB_DB
def test_a_datum_the_write_does_not_take_is_not_on_the_card():
    """A datum the write does not know («colour») is not saved, so the card does not show it: the line is said as the
    write takes it, by its field's name and its value in words."""
    field = CustomField.objects.create(name="VIP", field_type="boolean")
    card = Customer.objects.create(name="Lucía QA")
    lines = [{"field_id": str(field.id), "value": "true", "colour": "green"}]
    said = fields_of(UPDATE, {"id": str(card.id), "field_values": lines})["field_values"]
    assert (said["value"], said.get(NAMED)) == ([{"field_id": "VIP", "value": "Yes"}], True)
