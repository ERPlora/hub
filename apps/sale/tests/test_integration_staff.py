"""Sale and Staff together, no mocks (SALE-F16): a sale left on «Me» is attributed to the Staff record of
whoever holds the session, so it counts in the close per professional (``sale.sale.by_staff``) and in
Staff's commissions.

Sales does not require Staff: it asks Staff by the name of its operation (``staff.member.current``,
which needs no Staff permission: a cashier may sell without seeing the team). Whoever the charge names
wins; a line with its own professional keeps it; without a record, without a user behind the session or
without Staff, the sale counts for nobody, as before. Every sale is charged by card: a cash charge would
ask Cash register for an open drawer (SALE-F08), which is not what these tests are about.
"""

import dataclasses

import pytest
from live.context import system_context
from live.errors import AppInactive
from live.models import OutboxEvent
from live.operations import registry

from apps.sale.tests.conftest import A, ctx_for, run

pytestmark = pytest.mark.django_db

CARD = [{"method": "card"}]
CURRENT = "staff.member.current"


@pytest.fixture
def catalog(product):
    product("Shampoo", "SHP", 1210, "product.generic")
    product("Comb", "CMB", 605, "product.generic")


@pytest.fixture
def cashier(make_user):
    """Bea, an employee whose hub account is linked to her Staff record (made by Staff)."""
    user = make_user("bea", role="hub_employee")
    record = run(
        "staff.member.create",
        {"first_name": "Bea", "last_name": "Ruiz", "user_id": str(user.person.pk)},
        system_context(A),
    )
    return user, record


def member(first_name: str):
    return run("staff.member.create", {"first_name": first_name, "last_name": "López"}, system_context(A))


def as_user(user, role: str = "hub_employee", permissions=None):
    ctx = ctx_for(role, actor=user)
    return ctx if permissions is None else dataclasses.replace(ctx, permissions=frozenset(permissions))


def charge(ctx, key: str = "attempt-0001", **data):
    return run("sale.sale.complete", {"idempotency_key": key, "payments": CARD, **data}, ctx)


def by_staff():
    return {row.staff_id: row.total_revenue for row in run("sale.sale.by_staff", {}).rows}


def completed_staff_id():
    return OutboxEvent.objects.get(name="sale.sale.completed").payload["staff_id"]


# «Me» is the record of whoever holds the session


def test_a_counter_sale_left_on_me_is_attributed_to_the_record_of_whoever_charges_it(catalog, cashier):
    # flow: SALE-F16 (atribuir a quien tiene la sesión con «Atiende yo»)
    user, bea = cashier
    sale = charge(as_user(user), lines=[{"product": "SHP"}])
    assert sale.staff_id == bea.id
    assert sale.lines[0].staff_id is None  # a line of the check: it goes with the sale
    assert completed_staff_id() == str(bea.id)
    assert by_staff() == {bea.id: 1210}


def test_an_open_check_left_on_me_is_attributed_the_same(catalog, cashier):
    user, bea = cashier
    order = run("sale.order.open", {"lines": [{"product": "SHP"}, {"product": "CMB"}]}, as_user(user))
    sale = charge(as_user(user), order_id=str(order.id))
    assert sale.staff_id == bea.id
    assert by_staff() == {bea.id: 1815}


def test_the_managers_door_attributes_it_too(catalog, cashier):
    user, bea = cashier
    sale = run(
        "sale.sale.complete_over_limit",
        {"idempotency_key": "attempt-0001", "lines": [{"product": "SHP"}], "payments": CARD},
        as_user(user, "hub_manager"),
    )
    assert sale.staff_id == bea.id


def test_a_cashier_who_cannot_see_the_team_is_attributed_all_the_same(catalog, cashier):
    user, bea = cashier
    # An employee's permissions without any of Staff's: she sells, but does not see the team.
    employee = as_user(user)
    till_only = as_user(user, permissions={p for p in employee.permissions if not p.startswith("staff.")})
    assert employee.has("staff.view") and not till_only.has("staff.view")
    assert charge(till_only, lines=[{"product": "SHP"}]).staff_id == bea.id


# Whoever the charge names, and a line's own professional, are never replaced


def test_whoever_the_charge_names_wins_over_whoever_holds_the_session(catalog, cashier):
    user, _bea = cashier
    ana = member("Ana")
    sale = charge(as_user(user), lines=[{"product": "SHP"}], staff_id=str(ana.id))
    assert sale.staff_id == ana.id
    assert by_staff() == {ana.id: 1210}


def test_a_line_with_its_own_professional_keeps_it_and_the_rest_goes_to_me(catalog, cashier):
    user, bea = cashier
    ana = member("Ana")
    sale = charge(
        as_user(user),
        lines=[{"product": "SHP", "staff_id": str(ana.id)}, {"product": "CMB"}],
    )
    assert [line.staff_id for line in sale.lines] == [ana.id, None]
    assert sale.staff_id == bea.id
    assert by_staff() == {ana.id: 1210, bea.id: 605}


# Nobody to attribute it to: the sale counts for nobody, as before


def test_without_a_record_linked_to_the_session_the_sale_counts_for_nobody(catalog, make_user):
    user = make_user("carla", role="hub_employee")
    member("Ana")  # somebody else's record: never taken for hers
    sale = charge(as_user(user), lines=[{"product": "SHP"}])
    assert sale.staff_id is None
    assert completed_staff_id() is None
    assert by_staff() == {}


def test_the_platform_attributes_it_to_nobody(catalog, cashier):
    sale = charge(system_context(A), lines=[{"product": "SHP"}])
    assert sale.staff_id is None


@pytest.fixture(params=["absent", "off"])
def staff_unavailable(request, monkeypatch):
    """A business without Staff: its operation is not there (not installed), or it answers that the app
    is off for this hub (``app_inactive``)."""
    if request.param == "absent":
        monkeypatch.delitem(registry, CURRENT)
    else:

        def off(ctx, data):
            raise AppInactive("Staff is off.")

        monkeypatch.setitem(registry, CURRENT, dataclasses.replace(registry[CURRENT], fn=off))


def test_without_staff_the_till_still_charges_and_the_sale_counts_for_nobody(catalog, cashier, staff_unavailable):
    user, _bea = cashier
    sale = charge(as_user(user), lines=[{"product": "SHP"}])
    assert (sale.status, sale.staff_id) == ("completed", None)
