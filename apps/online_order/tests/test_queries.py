"""The tables' codes: every table of Tables in the floor plan's order, with its code and the address of its page once it
has one, read with the permission of whoever asks (this app's and Tables' own)."""

import pytest
from django.test import RequestFactory
from live.errors import PermissionDenied

from base.tenancy.context import use_hub

from .conftest import HOST, HUB_DB, A, B, ctx_for, make_table, make_zone, run

pytestmark = HUB_DB


def codes(ctx=None, **params):
    return run("online_order.qr_code.list", params, ctx)


def regenerate(table) -> str:
    return run("online_order.qr_code.regenerate", {"id": str(table.id)}).code


def test_every_table_comes_in_the_floor_plan_s_order_with_its_zone_and_no_code_until_one_is_generated():
    terrace = make_zone("Terrace")
    make_table("10", terrace)
    make_table("2", terrace)
    alone = make_table("1")
    page = codes()
    assert [(row.number, row.table, row.zone_name, row.code, row.url, row.issued_at) for row in page.rows] == [
        ("1", "1 (no zone)", None, None, None, None),
        ("2", "2 (Terrace)", "Terrace", None, None, None),
        ("10", "10 (Terrace)", "Terrace", None, None, None),
    ]
    assert page.rows[0].table_id == alone.id
    assert (page.total, page.limit, page.offset) == (3, 50, 0)


def test_a_table_with_a_code_shows_it_and_the_address_of_its_page(settings):
    settings.HUB_BASE_DOMAIN = "erplora.com"
    with_code, without = make_table("4"), make_table("5")
    made = run("online_order.qr_code.regenerate", {"id": str(with_code.id)})
    rows = {row.table_id: row for row in codes().rows}
    assert (rows[with_code.id].code, rows[with_code.id].issued_at) == (made.code, made.issued_at)
    assert rows[with_code.id].url == f"https://{A.key}.erplora.com/p/{A.key}/order/{made.code}"
    assert (rows[without.id].code, rows[without.id].url) == (None, None)


def test_the_address_is_the_one_the_browser_reached(settings):
    settings.ALLOWED_HOSTS = [".localhost"]
    code = regenerate(make_table("4"))
    request = RequestFactory().get("/api/online_order/qr_codes", HTTP_HOST=f"{HOST}:8000")
    [row] = codes(ctx_for(request=request)).rows
    assert row.url == f"http://{HOST}:8000/p/{A.key}/order/{code}"


def test_a_deleted_table_is_not_listed_even_with_a_code():
    gone = make_table("9")
    regenerate(gone)
    gone.is_deleted = True
    gone.save(update_fields=["is_deleted"])
    make_table("1")
    assert [row.number for row in codes().rows] == ["1"]


def test_the_list_comes_in_pages():
    for number in ("1", "2", "3"):
        regenerate(make_table(number))
    page = codes(limit=2, offset=1)
    assert ([row.number for row in page.rows], page.total, page.limit, page.offset) == (["2", "3"], 3, 2, 1)
    assert all(row.code for row in page.rows)


def test_an_employee_does_not_see_the_codes():
    make_table("1")
    with pytest.raises(PermissionDenied):
        codes(ctx_for("hub_employee"))


def test_whoever_cannot_see_the_tables_does_not_see_their_codes():
    make_table("1")
    with pytest.raises(PermissionDenied):
        codes(ctx_for(permissions={"online_order.view_qr_code"}))


def test_a_manager_sees_the_codes():
    code = regenerate(make_table("1"))
    assert [row.code for row in codes(ctx_for("hub_manager")).rows] == [code]


def test_a_business_sees_only_its_own_tables_and_codes(hub_b):
    in_a = make_table("1")
    regenerate(in_a)
    with use_hub(hub_b):
        in_b = make_table("1")
        [row] = codes(ctx_for(scope=B)).rows
    assert (row.table_id, row.code) == (in_b.id, None)
    [mine] = codes().rows
    assert (mine.table_id, bool(mine.code)) == (in_a.id, True)
