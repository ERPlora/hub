"""The list of the people who serve the room: searched by part of their name, a page of their id and name."""

from apps.table.schemas.waiters import WaiterListIn, WaiterOut, WaiterPage

from .test_schemas_fields import bad


def test_a_waiter_is_searched_by_part_of_their_name_and_nothing_else():
    assert WaiterListIn.model_validate({"search": "Ana"}).search == "Ana"
    assert bad(WaiterListIn, search="x" * 129)
    assert bad(WaiterListIn, name="Ana")


def test_a_page_of_waiters_lists_each_one_by_id_and_name():
    page = WaiterPage.model_validate(
        {"rows": [{"id": "u-1", "name": "Ana"}], "total": 1, "limit": 50, "offset": 0}
    )
    assert page.rows == [WaiterOut(id="u-1", name="Ana")]
