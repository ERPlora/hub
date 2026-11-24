"""What the schemas of Menus share: an input refuses a field it does not declare, and money is in whole cents."""

from apps.combo.schemas.choices import OptionIn
from apps.combo.schemas.menus import ComboIn

from .schema_checks import ID, refused


def test_an_unknown_field_is_refused():
    assert "hub_id" in refused(ComboIn, {"name": "x", "hub_id": "a"})


def test_a_menu_price_is_whole_cents_never_negative():
    assert "price" in refused(ComboIn, {"name": "x", "price": -1})
    assert "price" in refused(ComboIn, {"name": "x", "price": 12.5})
    assert ComboIn.model_validate({"name": "x"}).price == 0


def test_a_supplement_may_be_negative():
    assert (
        OptionIn.model_validate(
            {"group_id": ID, "product_id": ID, "price_delta": -50}
        ).price_delta
        == -50
    )
