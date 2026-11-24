"""The customer tag list (CUSTOMER-F28): how many live cards have each tag, and its filters."""

from apps.customer.models import CustomerTag
from apps.customer.schemas.tags import TagListIn

from .conftest import HUB_DB, card, run


pytestmark = HUB_DB


def test_the_tag_list():
    moroso = CustomerTag.objects.create(name="Moroso", color="danger")
    CustomerTag.objects.create(name="Nuevo")
    card("Ana").tags.add(moroso)
    page = run("customer.tag.list", TagListIn(sort="customer_count", descending=True))
    assert [(row.name, row.color, row.customer_count) for row in page.rows] == [
        ("Moroso", "danger", 1),
        ("Nuevo", "primary", 0),
    ]
    assert [
        row.name for row in run("customer.tag.list", TagListIn(color="danger")).rows
    ] == ["Moroso"]
