"""The departments of the open price and the quick notes of a line."""

from apps.sale.models.departments import Department, QuickNote
from apps.sale.tests.conftest import HUB_DB
from apps.tax.models import TaxCategory

pytestmark = HUB_DB


def test_departments_and_quick_notes_are_deleted_logically():
    category = TaxCategory.objects.get(key="product.reduced")
    department = Department.objects.create(
        name="Fruit", tax_category=category, sort_order=10
    )
    note = QuickNote.objects.create(text="no salt", sort_order=10)
    assert department.is_deleted is False and department.deleted_at is None
    assert note.is_deleted is False and note.deleted_at is None
    # Two departments may share one tax category.
    Department.objects.create(name="Veg", tax_category=category)
