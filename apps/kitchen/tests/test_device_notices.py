"""KITCHEN-F05/F16: every new kitchen ticket tells the installed device once.

The shared shell delivers the rows of ``base.notice.list`` and opens the route on a tap. Sales and
Inventory run for real: a round is told even before the relay saves it, and saving it never repeats it.
"""

import datetime as dt

import pytest
from live.context import Scope, system_context
from live.operations import get

from base.schemas import NoticeListIn
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

from .conftest import A, add_line, ctx_for, fire, fired_round, open_check, run

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def kitchen_on(monkeypatch):
    monkeypatch.setattr(
        "base.queries.active_apps",
        lambda scope: frozenset({"base", "kitchen", "sale", "inventory"}),
    )


def notices(ctx=None):
    operation = get("base.notice.list")
    return operation(ctx or ctx_for(), NoticeListIn()).model_dump(mode="json")["notices"]


def save_everything():
    return run("kitchen.ticket.sync", {}, system_context(A))


def test_a_round_fired_by_sales_tells_the_device_before_and_after_it_is_saved(clock, product):
    _order, lines = fired_round(product, "Burger", "Fries", label="Table 4")

    told = notices()
    assert [(notice["key"], notice["id"]) for notice in told] == [
        ("kitchen.received", str(lines[0].id))
    ]
    assert told[0]["title"] == "New kitchen ticket · Table 4"
    assert told[0]["body"] == "Burger, Fries · Waiter: waiter"
    assert told[0]["route"] == "/kitchen/display"
    assert dt.datetime.fromisoformat(told[0]["at"]) == clock.now

    save_everything()
    assert [(notice["key"], notice["id"]) for notice in notices()] == [
        ("kitchen.received", str(lines[0].id))
    ]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_round_fired_in_b_never_tells_a(hub_a, hub_b):
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_b):
        dish = run(
            "inventory.product.create",
            {"name": "Burger", "sku": "BURGER", "price": 1200, "tax_category_key": "restaurant.food"},
            in_b,
        )
        order = open_check("Table B", ctx=in_b)
        add_line(order.id, dish, ctx=in_b)
        fire(order.id, ctx=in_b)
        [told] = notices(in_b)
        assert (told["key"], told["title"]) == ("kitchen.received", "New kitchen ticket · Table B")
    with use_hub(hub_a):
        assert notices(in_a) == []


def test_every_new_ticket_is_told_once_newest_first_including_one_made_by_hand(clock, product):
    _order, lines = fired_round(product, "Burger", label="Table 4")
    save_everything()
    clock.advance(minutes=2)
    made = run(
        "kitchen.ticket.create",
        {"items": [{"name": "Staff meal"}], "label": ""},
    )

    told = notices()
    assert [(notice["key"], notice["id"]) for notice in told] == [
        ("kitchen.received", str(made.id)),
        ("kitchen.received", str(lines[0].id)),
    ]
    assert told[0]["title"] == f"New kitchen ticket · {made.number}"
    assert told[0]["body"] == "Staff meal · Waiter: tester"


def test_the_notice_uses_the_persons_language(clock, product):
    fired_round(product, "Burger", "Fries", label="Mesa 4")

    [told] = notices(ctx_for(language="es"))

    assert told["title"] == "Nueva comanda · Mesa 4"
    assert told["body"] == "Burger, Fries · Camarero: waiter"


def test_the_notice_window_and_limit(clock, product):
    fired_round(product, "Burger", label="Table 4")
    save_everything()
    clock.advance(minutes=1)
    _other, other_lines = fired_round(product, "Soup", label="Table 9")
    save_everything()

    page = run("kitchen.ticket.notices", {"limit": 1})
    assert [row.id for row in page.rows] == [other_lines[0].id]
    later = clock.advance(minutes=5).isoformat()
    assert run("kitchen.ticket.notices", {"since": later}).rows == []
    clock.advance(hours=25)
    assert notices() == []


def test_whoever_sees_kitchen_hears_it_and_nobody_else():
    operation = get("base.notice.list")
    assert operation(ctx_for("hub_employee"), NoticeListIn()).sources == ["kitchen.received"]
    assert operation(ctx_for("hub_employee", permissions={"base.view_home"}), NoticeListIn()).sources == []
