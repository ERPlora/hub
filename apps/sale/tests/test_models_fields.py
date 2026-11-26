"""The fields the sale app's models share: who did something, a JSON list and a percentage's range."""

from django.db.models import Q

from apps.sale.models.fields import ACTOR_MAX_LENGTH, _actor, _json_list, _percent_range


def test_who_did_something_is_optional_and_as_long_as_an_actors_name():
    field = _actor("voided by")
    assert (field.verbose_name, field.max_length, field.blank) == ("voided by", ACTOR_MAX_LENGTH, True)


def test_a_json_list_starts_empty_also_for_a_row_inserted_without_it():
    field = _json_list("allergens")
    assert (field.get_default(), field.db_default, field.blank) == ([], [], True)


def test_a_percentage_runs_from_0_to_100_on_the_field_it_names():
    assert _percent_range("discount_range").condition == Q(discount_percent__gte=0, discount_percent__lte=100)
    assert _percent_range("rate_range", "rate").condition == Q(rate__gte=0, rate__lte=100)
