"""The categories of the catalog: their list by order and name with their offered services, and one by its id or name."""

import pytest
from live.errors import NotFound

from apps.service.schemas.categories import CategoryListIn
from apps.service.schemas.fields import CategoryRefIn

from .conftest import HUB_DB, make_category, make_service, names, run

pytestmark = HUB_DB


def test_categories_list_by_order_and_name_with_their_offered_services(tax):
    hair = make_category("Hair", sort_order=2)
    nails = make_category("Nails", sort_order=1)
    colour = make_category("Colour", parent=hair, sort_order=2)
    make_category("Gone", is_deleted=True)
    make_service("Cut", tax=tax, category=hair)
    make_service("Perm", tax=tax, category=hair, is_active=False)
    page = run("service.category.list", CategoryListIn())
    assert names(page) == ["Nails", "Colour", "Hair"]
    assert [(row.name, row.parent_name, row.service_count) for row in page.rows] == [
        ("Nails", None, 0),
        ("Colour", "Hair", 0),
        ("Hair", None, 1),
    ]
    assert names(run("service.category.list", CategoryListIn(search="ai"))) == ["Nails", "Hair"]
    assert names(run("service.category.list", CategoryListIn(parent_id=hair.id))) == [
        "Colour"
    ]
    assert names(
        run("service.category.list", CategoryListIn(sort="-service_count"))
    ) == ["Hair", "Colour", "Nails"]
    assert run("service.category.get", CategoryRefIn(category="colour")).id == colour.id
    assert run("service.category.get", CategoryRefIn(id=nails.id)).name == "Nails"


def test_a_deleted_category_is_not_found():
    gone = make_category("Gone", is_deleted=True)
    with pytest.raises(NotFound) as missing:
        run("service.category.get", CategoryRefIn(id=gone.id))
    assert missing.value.code == "service.category_not_found"
