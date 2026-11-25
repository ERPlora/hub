"""The inputs of a choice: its product and its course, what a change replaces, the order of the choices and the product
that Inventory deletes."""

import uuid

from apps.combo.schemas.choices import DropProductIn, OptionBulkIn, OptionIn, OptionPatchIn, OptionReorderIn

from .schema_checks import ID, refused


def test_a_choice_names_its_product_and_its_course():
    option = OptionIn.model_validate(
        {"combo": "Menu of the day", "group": "Starters", "product": "Lentils"}
    )
    assert (option.price_delta, option.is_available) == (0, True)
    assert refused(OptionIn, {"combo": "Menu of the day", "group": "Starters"})
    assert refused(OptionIn, {"product": "Lentils"})


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


def test_the_reaction_reads_inventorys_deleted_product_payload():
    payload = {"id": ID, "sku": "FLAN", "name": "Flan"}
    assert DropProductIn.model_validate(payload).id == uuid.UUID(ID)
