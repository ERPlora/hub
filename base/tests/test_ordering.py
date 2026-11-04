"""The order of a list that sorts both ways (``base/ordering.py``, the rule of hub#2355)."""

from django.db.models import F

from base.ordering import list_order


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
