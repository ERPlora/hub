"""The inputs of the till: the menus on sale, the picks of one and the line that is priced."""

from apps.combo.schemas.till import ChoiceIn, ForSaleIn, ResolveIn

from .schema_checks import ID, refused


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


def test_a_pick_may_travel_as_json_text_in_a_query_string():
    line = ResolveIn.model_validate({"id": ID, "choices": ['{"product": "Flan", "quantity": 2}']})
    assert (line.choices[0].product, line.choices[0].quantity) == ("Flan", 2)
    assert "choices.0" in refused(ResolveIn, {"id": ID, "choices": ["not json"]})
