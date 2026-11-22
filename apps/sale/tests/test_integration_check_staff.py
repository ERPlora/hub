"""Who serves an open check (SALE-F16) belongs to the check and is kept in the Hub, not on one screen: read back when
the check is opened again (from the floor plan, from «Open checks» or on another device), it names the person chosen
until the check is charged. The kitchen ticket goes out with their name and the sale is theirs, unless whoever sends
or charges names somebody else. Sales and Staff together, no mocks; every sale is charged by card, as a cash charge
would ask Cash register for an open drawer."""

import dataclasses
import uuid

import pytest
from live.context import system_context
from live.errors import AppInactive, Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import registry

from apps.sale.tests.conftest import HUB_DB, A, B, ctx_for, run
from base.tenancy.context import use_hub

pytestmark = HUB_DB

CARD = [{"method": "card"}]
DETAIL = "staff.member.detail"


@pytest.fixture
def catalog(product):
    product("Coffee", "COF", 150, "product.generic")
    product("Water", "WAT", 200, "product.generic")


def member(first_name: str, last_name: str = "López", scope=A):
    return run("staff.member.create", {"first_name": first_name, "last_name": last_name}, system_context(scope))


def reopened(order):
    """The check as any till reads it again from the Hub."""
    return run("sale.order.get", {"order_id": str(order.id)})


def served(order) -> tuple:
    check = reopened(order)
    return check.staff_id, check.staff_name


def set_staff(order, staff_id, ctx=None):
    return run("sale.order.set_staff", {"order_id": str(order.id), "staff_id": staff_id and str(staff_id)}, ctx)


def fired_waiter(order, ctx=None, **data) -> str:
    OutboxEvent.objects.filter(name="sale.order.fired").delete()
    run("sale.order.fire", {"order_id": str(order.id), **data}, ctx)
    return OutboxEvent.objects.get(name="sale.order.fired").payload["waiter"]


def charge(order, key: str, **data):
    return run(
        "sale.sale.complete", {"idempotency_key": key, "order_id": str(order.id), "payments": CARD, **data}
    )


# Kept with the check


def test_a_check_opened_for_somebody_reads_back_who_serves_it(catalog):
    lucia = member("Lucia", "Garcia")
    order = run("sale.order.open", {"staff_id": str(lucia.id), "lines": [{"product": "COF"}]})
    assert (order.staff_id, order.staff_name) == (lucia.id, "Lucia Garcia")
    assert served(order) == (lucia.id, "Lucia Garcia")


def test_choosing_who_serves_an_open_check_is_kept_and_me_clears_it(catalog):
    lucia = member("Lucia", "Garcia")
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    assert served(order) == (None, "")
    OutboxEvent.objects.all().delete()

    answered = set_staff(order, lucia.id)
    assert (answered.staff_id, answered.staff_name, answered.version) == (lucia.id, "Lucia Garcia", order.version + 1)
    assert served(order) == (lucia.id, "Lucia Garcia")
    # Every till showing the check follows it.
    assert OutboxEvent.objects.filter(name="sale.order.changed", payload__order_id=str(order.id)).exists()

    set_staff(order, None)
    assert served(order) == (None, "")


def test_the_lines_already_on_the_check_keep_whoever_they_had(catalog):
    lucia, ana = member("Lucia", "Garcia"), member("Ana")
    order = run("sale.order.open", {"lines": [{"product": "COF", "staff_id": str(ana.id)}, {"product": "WAT"}]})
    set_staff(order, lucia.id)
    assert [line.staff_id for line in reopened(order).lines] == [ana.id, None]


def test_who_serves_a_closed_check_is_not_changed(catalog):
    lucia = member("Lucia", "Garcia")
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    run("sale.order.void", {"order_id": str(order.id)})
    with pytest.raises(Conflict) as refused:
        set_staff(order, lucia.id)
    assert refused.value.code == "sale.order_unavailable"


def test_somebody_who_is_not_on_the_team_is_refused_and_the_check_stays_as_it_was(catalog):
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    with pytest.raises(NotFound):
        set_staff(order, uuid.uuid4())
    with pytest.raises(NotFound):
        run("sale.order.open", {"staff_id": str(uuid.uuid4()), "lines": [{"product": "WAT"}]})
    assert served(order) == (None, "")
    assert run("sale.order.list", {}).total == 1


def test_someone_who_may_not_sell_cannot_say_who_serves_a_check(catalog):
    lucia = member("Lucia", "Garcia")
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    ctx = ctx_for()
    no_selling = dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - {"sale.add_sale"})
    with pytest.raises(PermissionDenied):
        set_staff(order, lucia.id, no_selling)
    assert served(order) == (None, "")


@pytest.fixture(params=["absent", "off"])
def staff_unavailable(request, monkeypatch):
    """A business without Staff: its read is not there (not installed), or it answers that the app is off."""
    if request.param == "absent":
        monkeypatch.delitem(registry, DETAIL)
    else:

        def off(ctx, data):
            raise AppInactive("Staff is off.")

        monkeypatch.setitem(registry, DETAIL, dataclasses.replace(registry[DETAIL], fn=off))


def test_without_staff_nobody_can_be_chosen_but_me_still_works(catalog, staff_unavailable):
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    with pytest.raises(Conflict) as refused:
        set_staff(order, uuid.uuid4())
    assert refused.value.code == "sale.staff_unavailable"
    assert set_staff(order, None).staff_id is None


# What the check's server is used for


def test_the_kitchen_ticket_names_who_serves_the_check_unless_the_till_names_somebody_else(
    catalog, django_user_model
):
    luis = django_user_model.objects.create_user("saas:45", first_name="Luis", last_name="Pérez")
    sender = ctx_for(actor=luis)
    lucia = member("Lucia", "Garcia")
    order = run("sale.order.open", {"staff_id": str(lucia.id), "lines": [{"product": "COF"}]})
    assert fired_waiter(order, sender) == "Lucia Garcia"

    run("sale.order.add_line", {"order_id": str(order.id), "product": "WAT"})
    assert fired_waiter(order, sender, waiter="Marta Ruiz") == "Marta Ruiz"

    set_staff(order, None)
    run("sale.order.add_line", {"order_id": str(order.id), "product": "COF"})
    assert fired_waiter(order, sender) == "Luis Pérez"


def test_the_sale_of_the_check_is_who_serves_it_unless_the_charge_names_somebody_else(catalog):
    lucia, ana = member("Lucia", "Garcia"), member("Ana")
    order = run("sale.order.open", {"staff_id": str(lucia.id), "lines": [{"product": "COF"}, {"product": "WAT"}]})
    first, second = (str(line.id) for line in order.lines)

    part = charge(order, "check-staff-0001", line_ids=[first])
    assert (part.staff_id, part.lines[0].staff_id) == (lucia.id, None)

    rest = charge(order, "check-staff-0002", line_ids=[second], staff_id=str(ana.id))
    assert rest.staff_id == ana.id


def test_a_split_check_keeps_who_serves_it(catalog):
    lucia = member("Lucia", "Garcia")
    order = run("sale.order.open", {"staff_id": str(lucia.id), "lines": [{"product": "COF"}, {"product": "WAT"}]})
    parts = run("sale.order.split", {"order_id": str(order.id), "line_ids": [str(order.lines[1].id)]})
    assert served(parts.new_order) == (lucia.id, "Lucia Garcia")
    assert served(parts.order) == (lucia.id, "Lucia Garcia")


def test_who_serves_is_somebody_of_the_business_of_the_check_and_stays_there(catalog, hub_b):
    in_b = ctx_for(scope=B)
    with use_hub(hub_b):
        bea = member("Bea", "Ruiz", scope=B)
        theirs = run("sale.order.open", {"staff_id": str(bea.id)}, in_b)
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    with pytest.raises(NotFound):
        set_staff(order, bea.id)
    assert served(order) == (None, "")
    with use_hub(hub_b):
        check = run("sale.order.get", {"order_id": str(theirs.id)}, in_b)
    assert (check.staff_id, check.staff_name) == (bea.id, "Bea Ruiz")
