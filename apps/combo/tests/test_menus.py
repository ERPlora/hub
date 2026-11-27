"""The inputs of a menu: what one is made or changed with, and how the list is read."""

from apps.combo.schemas.menus import ComboIn, ComboListIn, ComboPatchIn

from .schema_checks import refused


def test_a_menu_needs_a_name_and_takes_the_old_defaults():
    menu = ComboIn.model_validate(
        {
            "name": "  Menu of the day  ",
            "price": 1350,
            "tax_category_key": "restaurant.food",
        }
    )
    assert menu.name == "Menu of the day"
    assert (menu.kitchen_name, menu.supply_kind, menu.sort_order, menu.is_active) == (
        "",
        "service",
        0,
        True,
    )
    assert "name" in refused(ComboIn, {"name": "   "})


def test_a_menu_is_sold_eaten_in_or_to_take_away_and_nothing_else():
    assert "supply_kind" in refused(ComboIn, {"name": "x", "supply_kind": "mixed"})
    assert (
        ComboIn.model_validate({"name": "x", "price": 600, "supply_kind": "goods"}).supply_kind
        == "goods"
    )


def test_a_change_names_the_menu_and_sends_only_what_changes():
    patch = ComboPatchIn.model_validate({"combo": "Menu of the day", "price": 1400})
    assert patch.model_fields_set == {"combo", "price"}
    assert refused(ComboPatchIn, {"price": 1400})


def test_the_list_sorts_by_the_columns_of_the_table():
    params = ComboListIn.model_validate({})
    assert (params.sort, params.dir, params.limit, params.offset) == (
        "sort_order",
        "asc",
        50,
        0,
    )
    assert "sort" in refused(ComboListIn, {"sort": "created_by"})
    assert "limit" in refused(ComboListIn, {"limit": 101})
    assert "is_active" not in refused(ComboListIn, {"is_active": True, "unknown": 1})
