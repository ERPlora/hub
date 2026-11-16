"""The order of a list that sorts both ways (``base/ordering.py``)."""

from django.db.models import F
from django.db.models.functions import Lower

from base.ordering import list_order, list_order_for


def test_an_ascending_list_closes_with_the_id_ascending():
    assert list_order("name", descending=False) == [F("name").asc(), F("id").asc()]


def test_a_descending_list_is_the_ascending_one_read_backwards_ties_included():
    assert list_order("sort_order", "name", descending=True) == [
        F("sort_order").desc(),
        F("name").desc(),
        F("id").desc(),
    ]


def test_empty_values_stay_where_the_database_puts_them_unless_the_list_asks_for_them_last():
    assert [key.nulls_last for key in list_order("due", descending=True)] == [None, None]
    assert [key.nulls_last for key in list_order("due", descending=True, nulls_last=True)] == [True, True]
    assert [key.nulls_last for key in list_order("due", descending=False, nulls_last=True)] == [True, True]


def test_an_expression_goes_in_the_lists_direction_like_a_column():
    assert list_order(Lower("name"), descending=True) == [Lower("name").desc(), F("id").desc()]
    assert list_order(Lower("name"), descending=False) == [Lower("name").asc(), F("id").asc()]


def test_a_column_named_twice_counts_where_it_first_appears():
    assert list_order("name", "sort_order", "name", descending=True) == [
        F("name").desc(),
        F("sort_order").desc(),
        F("id").desc(),
    ]
    assert list_order("id", "name", descending=False) == [F("id").asc(), F("name").asc()]
    assert list_order(Lower("name"), Lower("name"), descending=False) == [Lower("name").asc(), F("id").asc()]


def test_a_leading_minus_is_a_descending_sort():
    assert list_order_for("name") == list_order("name", descending=False)
    assert list_order_for("-name") == list_order("name", descending=True)


def test_a_sort_can_stand_for_several_columns_and_any_other_is_the_column_itself():
    columns = {"starts_at": ("date", "time")}
    assert list_order_for("-starts_at", columns=columns) == list_order("date", "time", descending=True)
    assert list_order_for("name", columns=columns) == list_order("name", descending=False)


def test_a_sort_takes_its_ties_and_where_the_empty_values_go():
    assert list_order_for("-price", "name", nulls_last=True) == list_order(
        "price", "name", descending=True, nulls_last=True
    )
