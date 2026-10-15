"""The inputs of the combo operations: what is refused before anything is read (a 422 per field).

Every input refuses a field it does not declare. A menu is named by its id or its name; a course by
its id, or by its name inside a menu; a product by its id, its SKU or its name.
"""

import uuid

import pytest
from pydantic import ValidationError

from apps.combo.schemas import (
    ChoiceIn,
    ComboIn,
    ComboListIn,
    ComboPatchIn,
    ComboRefIn,
    DropProductIn,
    ForSaleIn,
    GroupIn,
    GroupPatchIn,
    GroupRefIn,
    GroupReorderIn,
    OptionBulkIn,
    OptionIn,
    OptionPatchIn,
    OptionRefIn,
    OptionReorderIn,
    ResolveIn,
)

ID = str(uuid.uuid7())


def fields_of(error: ValidationError) -> dict[str, str]:
    return {".".join(map(str, e["loc"])): e["msg"] for e in error.errors()}


def refused(schema, data) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return fields_of(caught.value)


# Menus


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


def test_a_menu_price_is_whole_cents_never_negative():
    assert "price" in refused(ComboIn, {"name": "x", "price": -1})
    assert "price" in refused(ComboIn, {"name": "x", "price": 12.5})
    assert ComboIn.model_validate({"name": "x"}).price == 0


def test_a_menu_is_sold_eaten_in_or_to_take_away_and_nothing_else():
    assert "supply_kind" in refused(ComboIn, {"name": "x", "supply_kind": "mixed"})
    assert (
        ComboIn.model_validate({"name": "x", "supply_kind": "goods"}).supply_kind
        == "goods"
    )


def test_an_unknown_field_is_refused():
    assert "hub_id" in refused(ComboIn, {"name": "x", "hub_id": "a"})


def test_a_menu_is_named_by_its_id_or_its_name():
    assert (
        ComboRefIn.model_validate({"combo": "menu of the day"}).combo
        == "menu of the day"
    )
    assert ComboRefIn.model_validate({"id": ID}).id == uuid.UUID(ID)
    assert refused(ComboRefIn, {})


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


# Courses


def test_a_course_defaults_to_one_compulsory_pick():
    course = GroupIn.model_validate({"combo": "Menu of the day", "name": "Starters"})
    assert (course.min_choices, course.max_choices, course.allow_repeat) == (
        1,
        1,
        False,
    )


def test_a_course_ceiling_below_its_floor_is_refused_on_the_maximum():
    fields = refused(
        GroupIn, {"combo_id": ID, "name": "Mains", "min_choices": 2, "max_choices": 1}
    )
    assert fields["max_choices"].endswith(
        "The maximum (1) is below the minimum (2): nobody could ever satisfy this course."
    )
    assert (
        GroupIn.model_validate(
            {"combo_id": ID, "name": "Drinks", "min_choices": 2, "max_choices": 0}
        ).max_choices
        == 0
    )


def test_a_course_asks_for_fifty_at_most():
    assert "min_choices" in refused(
        GroupIn, {"combo_id": ID, "name": "x", "min_choices": 51, "max_choices": 0}
    )
    assert "max_choices" in refused(
        GroupIn, {"combo_id": ID, "name": "x", "max_choices": 51}
    )


def test_a_course_belongs_to_a_menu_named_by_id_or_name():
    assert refused(GroupIn, {"name": "Starters"})


def test_a_course_is_named_by_its_id_or_by_its_name_in_a_menu():
    assert GroupRefIn.model_validate({"id": ID}).id == uuid.UUID(ID)
    assert (
        GroupRefIn.model_validate(
            {"combo": "Menu of the day", "group": "Starters"}
        ).group
        == "Starters"
    )
    assert refused(GroupRefIn, {"group": "Starters"})
    assert refused(GroupRefIn, {})


def test_a_course_change_checks_its_own_ceiling_when_both_are_sent():
    assert "max_choices" in refused(
        GroupPatchIn, {"id": ID, "min_choices": 3, "max_choices": 2}
    )
    assert GroupPatchIn.model_validate(
        {"id": ID, "max_choices": 2}
    ).model_fields_set == {"id", "max_choices"}


def test_reordering_courses_names_each_once():
    assert refused(GroupReorderIn, {"id": ID, "group_ids": [ID, ID]})
    assert refused(GroupReorderIn, {"id": ID, "group_ids": []})


# Choices


def test_a_choice_names_its_product_and_its_course():
    option = OptionIn.model_validate(
        {"combo": "Menu of the day", "group": "Starters", "product": "Lentils"}
    )
    assert (option.price_delta, option.is_available) == (0, True)
    assert refused(OptionIn, {"combo": "Menu of the day", "group": "Starters"})
    assert refused(OptionIn, {"product": "Lentils"})


def test_a_supplement_may_be_negative():
    assert (
        OptionIn.model_validate(
            {"group_id": ID, "product_id": ID, "price_delta": -50}
        ).price_delta
        == -50
    )


def test_a_choice_is_named_by_its_id_or_by_its_product_in_a_menu():
    assert OptionRefIn.model_validate({"id": ID}).id == uuid.UUID(ID)
    assert (
        OptionRefIn.model_validate(
            {"combo": "Menu of the day", "product": "Flan"}
        ).product
        == "Flan"
    )
    assert refused(OptionRefIn, {"product": "Flan"})
    assert refused(OptionRefIn, {})


def test_a_choice_change_may_replace_its_product():
    patch = OptionPatchIn.model_validate(
        {"id": ID, "new_product": "Hake", "price_delta": 200}
    )
    assert patch.model_fields_set == {"id", "new_product", "price_delta"}


def test_several_choices_at_once_name_each_product_once_forty_at_most():
    assert OptionBulkIn.model_validate(
        {"group_id": ID, "product_ids": [ID]}
    ).product_ids == [uuid.UUID(ID)]
    assert refused(OptionBulkIn, {"group_id": ID, "product_ids": [ID, ID]})
    assert refused(OptionBulkIn, {"group_id": ID, "product_ids": []})
    assert refused(
        OptionBulkIn,
        {"group_id": ID, "product_ids": [str(uuid.uuid7()) for _ in range(41)]},
    )


def test_reordering_choices_names_each_once():
    assert refused(OptionReorderIn, {"group_id": ID, "option_ids": [ID, ID]})


# The till


def test_the_till_reads_fifty_menus_at_most_a_page():
    assert ForSaleIn.model_validate({}).limit == 50
    assert "limit" in refused(ForSaleIn, {"limit": 51})


def test_a_pick_names_a_choice_or_a_product_and_a_count():
    assert ChoiceIn.model_validate({"product": "Flan"}).quantity == 1
    assert refused(ChoiceIn, {"quantity": 1})
    assert "quantity" in refused(ChoiceIn, {"option_id": ID, "quantity": 0})
    assert "quantity" in refused(ChoiceIn, {"option_id": ID, "quantity": 51})


def test_a_line_names_its_menu_and_may_carry_the_amount_ordered():
    line = ResolveIn.model_validate(
        {"combo": "Menu of the day", "choices": [{"product": "Flan"}], "amount": 1350}
    )
    assert line.amount == 1350
    assert "amount" in refused(ResolveIn, {"combo": "x", "amount": -1})
    assert ResolveIn.model_validate({"id": ID}).choices == []


def test_the_reaction_reads_inventorys_deleted_product_payload():
    payload = {"id": ID, "sku": "FLAN", "name": "Flan"}
    assert DropProductIn.model_validate(payload).id == uuid.UUID(ID)


def test_a_pick_may_travel_as_json_text_in_a_query_string():
    line = ResolveIn.model_validate({"id": ID, "choices": ['{"product": "Flan", "quantity": 2}']})
    assert (line.choices[0].product, line.choices[0].quantity) == ("Flan", 2)
    assert "choices.0" in refused(ResolveIn, {"id": ID, "choices": ["not json"]})
