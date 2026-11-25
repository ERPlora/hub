"""The values of a card's custom fields, saved with the card (CUSTOMER-F29)."""

import uuid

import pytest
from live.errors import InvalidPayload

from apps.customer import events
from apps.customer.models import CustomField, CustomFieldValue
from apps.customer.schemas.cards import CustomerPatchIn

from .conftest import HUB_DB, card, invalid, outbox, run, values

pytestmark = HUB_DB


# Custom field values on the update


@pytest.fixture
def fields(db):
    return {
        "allergies": CustomField.objects.create(name="Allergies", is_required=True),
        "visits": CustomField.objects.create(name="Visits", field_type="number"),
        "since": CustomField.objects.create(name="Since", field_type="date"),
        "vegan": CustomField.objects.create(name="Vegan", field_type="boolean"),
        "hair": CustomField.objects.create(
            name="Hair", field_type="select", options=["Short", "Long"]
        ),
        "old": CustomField.objects.create(name="Old", is_active=False),
    }


def field_values(fields, **sent):
    return [
        {"field_id": fields[name].id, "value": value} for name, value in sent.items()
    ]


def test_the_sheet_and_its_fields_are_saved_in_one_write(fields):
    ana = card("Ana")
    detail = run(
        "customer.customer.update",
        CustomerPatchIn(
            id=ana.id,
            notes="VIP",
            field_values=field_values(
                fields,
                allergies="Latex",
                visits="3.5",
                since="2024-02-29",
                vegan="true",
                hair="Long",
            ),
        ),
    )
    assert values(ana) == {
        "Allergies": "Latex",
        "Visits": "3.5",
        "Since": "2024-02-29",
        "Vegan": "true",
        "Hair": "Long",
    }
    assert {field.name: field.value for field in detail.custom_fields}["Hair"] == "Long"
    assert outbox() == [(events.CUSTOMER_UPDATED, {"id": str(ana.id)})]


def test_an_empty_value_clears_a_field_and_the_old_one_and_zero_still_read_as_booleans(
    fields,
):
    ana = card("Ana")
    CustomFieldValue.objects.create(
        customer=ana, field=fields["allergies"], value="Latex"
    )
    CustomFieldValue.objects.create(customer=ana, field=fields["visits"], value="3")
    run(
        "customer.customer.update",
        CustomerPatchIn(
            id=ana.id, field_values=field_values(fields, visits="", vegan="1")
        ),
    )
    assert values(ana) == {"Allergies": "Latex", "Vegan": "true"}


def test_a_required_field_is_satisfied_by_its_stored_value(fields):
    ana = card("Ana")
    CustomFieldValue.objects.create(
        customer=ana, field=fields["allergies"], value="Latex"
    )
    run(
        "customer.customer.update",
        CustomerPatchIn(id=ana.id, field_values=field_values(fields, hair="Short")),
    )
    assert values(ana)["Hair"] == "Short"


def test_a_required_field_left_empty_rejects_the_whole_save(fields):
    ana = card("Ana")
    with pytest.raises(InvalidPayload) as excinfo:
        run(
            "customer.customer.update",
            CustomerPatchIn(
                id=ana.id, name="Bea", field_values=field_values(fields, hair="Short")
            ),
        )
    status, code, errors = invalid(excinfo.value)
    assert (status, code, errors) == (
        422,
        "customer.field_required",
        {f"field_values.{fields['allergies'].id}": "This field is required."},
    )
    ana.refresh_from_db()
    assert (ana.name, values(ana)) == ("Ana", {})


@pytest.mark.parametrize(
    ("name", "value", "code", "message"),
    [
        ("visits", "three", "customer.field_invalid_number", "Enter a number."),
        ("visits", "nan", "customer.field_invalid_number", "Enter a number."),
        ("since", "2026-02-31", "customer.field_invalid_date", "Enter a valid date."),
        ("since", "14/10/2026", "customer.field_invalid_date", "Enter a valid date."),
        ("vegan", "maybe", "customer.field_invalid_boolean", "Choose yes or no."),
        (
            "hair",
            "Purple",
            "customer.field_invalid_option",
            "Choose one of the options.",
        ),
    ],
)
def test_a_value_that_does_not_fit_its_type_rejects_the_save(
    fields, name, value, code, message
):
    ana = card("Ana")
    sent = field_values(fields, allergies="Latex", **{name: value})
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.customer.update", CustomerPatchIn(id=ana.id, field_values=sent))
    assert invalid(excinfo.value) == (
        422,
        code,
        {f"field_values.{fields[name].id}": message},
    )
    assert values(ana) == {}


def test_an_unknown_or_inactive_field_is_unavailable(fields):
    ana = card("Ana")
    for field_id in (fields["old"].id, uuid.uuid7()):
        with pytest.raises(InvalidPayload) as excinfo:
            run(
                "customer.customer.update",
                CustomerPatchIn(
                    id=ana.id, field_values=[{"field_id": field_id, "value": "x"}]
                ),
            )
        status, code, errors = invalid(excinfo.value)
        assert (status, code, errors[f"field_values.{field_id}"]) == (
            422,
            "customer.field_unavailable",
            "That field no longer exists.",
        )


def test_without_field_values_the_required_fields_are_not_checked(fields):
    # Creating a card and a plain edit never ask for the custom fields (CUSTOMER-F29).
    ana = card("Ana")
    assert (
        run("customer.customer.update", CustomerPatchIn(id=ana.id, city="Madrid")).city
        == "Madrid"
    )
