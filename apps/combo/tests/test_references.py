"""A menu is named by its id or its name; a course by its id, or by its name inside a menu; a choice by its id, or by
its product inside a menu."""

import uuid

from apps.combo.schemas.references import ComboRefIn, GroupRefIn, OptionRefIn

from .schema_checks import ID, refused


def test_a_menu_is_named_by_its_id_or_its_name():
    assert (
        ComboRefIn.model_validate({"combo": "menu of the day"}).combo
        == "menu of the day"
    )
    assert ComboRefIn.model_validate({"id": ID}).id == uuid.UUID(ID)
    assert refused(ComboRefIn, {})


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
