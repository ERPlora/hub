"""The input of a zone: a name and a known colour."""

from apps.table.schemas.zones import ZoneIn

from .test_schemas_fields import bad


def test_a_zone_needs_a_name_and_a_known_colour():
    assert bad(ZoneIn, name="")
    assert bad(ZoneIn, name="Bar", color="pink")
    zone = ZoneIn.model_validate({"name": " Bar "})
    assert (zone.name, zone.color, zone.sort_order, zone.description) == (
        "Bar",
        "primary",
        None,
        "",
    )
