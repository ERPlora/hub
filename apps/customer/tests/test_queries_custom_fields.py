"""The list of the cards' custom fields (CUSTOMER-F29) and its filters."""

from apps.customer.models import CustomField
from apps.customer.schemas.custom_fields import FieldListIn

from .conftest import HUB_DB, run


pytestmark = HUB_DB


def test_the_field_list_and_its_filters():
    CustomField.objects.create(name="Allergies", is_required=True)
    CustomField.objects.create(name="Hair", field_type="select", options=["Short"])
    CustomField.objects.create(name="Old", is_active=False)
    assert [row.name for row in run("customer.field.list", FieldListIn()).rows] == [
        "Allergies",
        "Hair",
        "Old",
    ]
    assert [
        row.name
        for row in run("customer.field.list", FieldListIn(field_type="select")).rows
    ] == ["Hair"]
    assert [
        row.name
        for row in run("customer.field.list", FieldListIn(is_required=True)).rows
    ] == ["Allergies"]
    assert [
        row.name
        for row in run("customer.field.list", FieldListIn(is_active=False)).rows
    ] == ["Old"]
    assert run("customer.field.list", FieldListIn(search="hai")).rows[0].options == [
        "Short"
    ]
