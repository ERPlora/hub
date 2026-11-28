"""Every value the live cards keep in their custom fields, with the card and the field by name: what a backup of the
business carries of them. Only who may export the customers reads it."""

import pytest
from django.utils import timezone
from live.errors import PermissionDenied

from apps.customer.models import CustomField, CustomFieldValue
from apps.customer.schemas.fields import PageIn

from .conftest import HUB_DB, card, run

pytestmark = HUB_DB


def rows(page) -> list[tuple]:
    return [(row.customer, row.phone, row.email, row.field, row.value) for row in page.rows]


def test_each_value_comes_with_its_card_and_its_field_by_name_only_of_live_cards_and_active_fields():
    size = CustomField.objects.create(name="Shoe size", sort_order=1)
    allergies = CustomField.objects.create(name="Allergies", sort_order=2)
    old = CustomField.objects.create(name="Old field", is_active=False)
    lucia = card("Lucía Pérez", phone="+34600111222")
    gone = card("Gone", deleted_at=timezone.now())
    for customer, field, value in ((lucia, allergies, "Nuts"), (lucia, size, "38"), (lucia, old, "x"), (gone, size, "40")):
        CustomFieldValue.objects.create(customer=customer, field=field, value=value)

    page = run("customer.field_value.list", PageIn())

    assert rows(page) == [
        ("Lucía Pérez", "+34600111222", "", "Shoe size", "38"),
        ("Lucía Pérez", "+34600111222", "", "Allergies", "Nuts"),
    ]
    assert page.total == 2


def test_the_values_are_read_page_by_page():
    field = CustomField.objects.create(name="Allergies")
    for name in ("Ana", "Bea", "Carla"):
        CustomFieldValue.objects.create(customer=card(name), field=field, value="None")

    page = run("customer.field_value.list", PageIn(limit=2, offset=2))

    assert ([row.customer for row in page.rows], page.total) == (["Carla"], 3)


def test_only_who_may_export_the_customers_reads_them():
    with pytest.raises(PermissionDenied):
        run("customer.field_value.list", PageIn(), role="hub_employee")
