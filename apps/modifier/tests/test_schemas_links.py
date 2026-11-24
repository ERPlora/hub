"""The schemas of the links of a group: what one hangs from and what a reaction to Inventory takes (422 per field)."""

import uuid

from apps.modifier.schemas.links import DropIn, LinkIn, LinkRefIn

from .schema_checks import refused


def test_a_link_hangs_a_group_from_exactly_one_product_or_category():
    assert (
        LinkIn.model_validate({"group": "Sauces", "product": "BUR-01"}).product
        == "BUR-01"
    )
    assert (
        LinkIn.model_validate({"group": "Sauces", "category": "Mains"}).category
        == "Mains"
    )
    assert refused(LinkIn, group="Sauces") == {"__all__"}
    assert refused(LinkIn, group="Sauces", product="BUR-01", category="Mains") == {
        "__all__"
    }
    assert refused(LinkIn, product="BUR-01") == {"__all__"}
    assert LinkRefIn.model_validate({"id": str(uuid.uuid7())}).group is None
    assert refused(LinkRefIn, group="Sauces") == {"__all__"}


def test_a_reaction_takes_the_inventory_payload_as_it_is():
    row = uuid.uuid7()
    assert (
        DropIn.model_validate({"id": str(row), "sku": "BUR", "name": "Burger"}).id
        == row
    )
