"""``base.session.me`` with the real modules and roles: each role's menu, and so its «My apps», lists only the screens
it may open.

An employee has the apps of the floor (selling, the till, tables, kitchen, bookings, the agenda, customers, the time
clock…) and none of those that set the business up; the apps it does not open stay among its ``apps``, which other
screens read to know that an app is on (the till sells modifiers and menus).
"""

import pytest
from live.context import OperationContext
from live.meta import module_configs
from live.operations import get

from base import home
from base.permissions import access_for, permissions_of_role
from base.roles import APPROVAL, OFF, ON
from base.schemas.sessions import SessionMeIn
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.roles import a_role, held_by

__all__ = ["in_business_a"]

pytestmark = HUB_DB

#: The apps that set the business up: whoever manages them opens them, never an employee.
SETUP_APPS = {"tax", "pricing", "modifier", "combo", "payment", "schedule", "printing", "website"}
FLOOR_APPS = {
    "sale", "cash_register", "table", "kitchen", "reservation", "appointment", "customer", "attendance", "verifactu"
}


def menu_of(user, role: str) -> dict[str, list[str]]:
    me = session_me(user, role)
    return {group["id"]: [item["path"] for item in group["items"]] for group in me["menu"]}


def session_me(user, role: str) -> dict:
    ctx = OperationContext(scope=A, actor=user, permissions=permissions_of_role(role), language="en")
    return get("base.session.me")(ctx, SessionMeIn()).model_dump(mode="json")


def test_an_employee_has_the_apps_of_the_floor_and_none_that_set_up_the_business(make_user):
    menu = menu_of(make_user(), "hub_employee")
    assert FLOOR_APPS <= menu.keys()
    assert SETUP_APPS & menu.keys() == set()


def test_an_employee_s_menu_has_only_the_screens_of_its_work(make_user):
    menu = menu_of(make_user(), "hub_employee")
    assert menu["sale"] == ["/sale/pos", "/sale/sales"]
    assert menu["cash_register"] == ["/cash_register/sessions"]
    assert menu["invoice"] == ["/invoice/invoices"]
    assert menu["kitchen"] == ["/kitchen/display", "/kitchen/tickets", "/kitchen/history"]
    assert menu["table"] == ["/table/floor-plan", "/table/sessions"]
    assert menu["customer"] == ["/customer/customers"]
    assert menu["reservation"] == ["/reservation/reservations", "/reservation/waitlist"]
    assert menu["staff"] == ["/staff/members", "/staff/time-off", "/staff/schedules", "/staff/commissions"]
    assert menu["flow"] == ["/flow/automations"]
    assert menu["online_booking"] == ["/online_booking/bookings"]
    assert menu["whatsapp_inbox"] == ["/whatsapp_inbox/inbox"]
    assert menu["task"] == ["/task/tasks", "/task/projects"]
    assert menu["cart_checkout"] == ["/cart_checkout/carts", "/cart_checkout/orders"]
    assert menu["verifactu"] == [
        "/verifactu/records", "/verifactu/contingency", "/verifactu/events", "/verifactu/recovery"
    ]


def test_the_apps_an_employee_does_not_open_stay_on_for_the_screens_that_read_them(make_user):
    states = {app["label"]: app["state"] for app in session_me(make_user(), "hub_employee")["apps"]}
    assert (states["modifier"], states["combo"], states["tax"]) == ("on", "on", "on")


def test_a_manager_opens_the_setup_apps_except_what_only_the_owner_and_admin_set_up(make_user):
    menu = menu_of(make_user(), "hub_manager")
    assert SETUP_APPS - {"website"} <= menu.keys()
    assert "website" not in menu
    assert menu["verifactu"] == ["/verifactu/records", "/verifactu/contingency", "/verifactu/events", "/verifactu/recovery"]
    assert menu["invoice"] == ["/invoice/invoices", "/invoice/series"]


def test_the_owner_and_the_admin_open_every_screen_of_every_app(make_user):
    every = {
        config.label: [nav.path for nav in config.navigation]
        for config in home.shown_modules.shown_modules(demo_hub=False)
        if config.navigation
    }
    assert menu_of(make_user("olga"), "hub_owner") == every
    assert menu_of(make_user("adrian"), "hub_admin") == every
    assert every.keys() == {config.label for config in module_configs() if config.navigation}


def test_the_screens_an_employee_may_not_open_are_locked_under_their_app(make_user):
    locked = session_me(make_user(), "hub_employee")["locked"]
    assert locked["tax"] == ["/tax/categories", "/tax/rules", "/tax/aliases", "/tax/settings"]
    assert locked["verifactu"] == ["/verifactu/config", "/verifactu/settings"]
    assert "/sale/pos" not in locked.get("sale", [])


def test_every_screen_of_an_app_is_either_open_in_the_menu_or_locked(make_user):
    for username, role in (("eva", "hub_employee"), ("mario", "hub_manager")):
        me = session_me(make_user(username), role)
        menu = {group["id"]: [item["path"] for item in group["items"]] for group in me["menu"]}
        for config in home.shown_modules.shown_modules(demo_hub=False):
            opened, closed = menu.get(config.label, []), me["locked"].get(config.label, [])
            assert sorted(opened + closed) == sorted(nav.path for nav in config.navigation), (role, config.label)
            assert role != "hub_employee" or config.label not in SETUP_APPS or not opened, config.label


def test_nothing_is_locked_to_the_owner_or_the_admin(make_user):
    assert session_me(make_user("olga"), "hub_owner")["locked"] == {}
    assert session_me(make_user("adrian"), "hub_admin")["locked"] == {}


# ── the role of the person and what a manager may approve for them ────────────────────────────────────────────────


def signed_in(user, language="en") -> dict:
    ctx = OperationContext(scope=A, actor=user, permissions=access_for(user, A), language=language)
    return get("base.session.me")(ctx, SessionMeIn()).model_dump(mode="json")


@pytest.mark.parametrize(
    ("role", "language", "name"),
    [("hub_owner", "en", "Owner"), ("hub_manager", "es", "Encargado"), ("hub_accountant", "es", "Gestoría")],
)
def test_the_role_of_the_invitation_is_named_in_the_persons_language(make_user, role, language, name):
    assert signed_in(make_user("saas:3", host=A.key, role=role), language)["role"] == name


def test_a_role_of_the_business_is_named_as_the_business_wrote_it(make_user):
    eva = make_user("saas:3", host=A.key, role="hub_employee")
    held_by(eva, a_role("Cajero sin anulaciones", sale__view_sale=ON))

    assert signed_in(eva)["role"] == "Cajero sin anulaciones"


def test_the_owner_keeps_the_name_of_their_role_whatever_role_their_row_names(make_user):
    olga = make_user("saas:1", host=A.key, role="hub_owner")
    held_by(olga, a_role("Cashier", sale__view_sale=ON))

    assert signed_in(olga)["role"] == "Owner"


def test_nobody_signed_in_has_no_role(make_user):
    stranger = make_user("saas:8")
    for actor in (None, stranger):
        me = signed_in(actor)
        assert (me["role"], me["approvable"]) == (None, [])


def test_what_a_manager_may_approve_for_a_basic_role_is_what_it_lacks(make_user):
    eva, adam = (make_user(f"saas:{n}", host=A.key, role=role) for n, role in ((3, "hub_employee"), (2, "hub_admin")))

    mine = signed_in(eva)

    assert "sale.void_sale" in mine["approvable"]
    assert not set(mine["approvable"]) & set(mine["permissions"])
    assert mine["approvable"] == sorted(mine["approvable"])
    assert signed_in(adam)["approvable"] == []


def test_what_a_manager_may_approve_for_a_role_of_the_business_is_what_it_leaves_with_approval(make_user):
    eva = make_user("saas:3", host=A.key, role="hub_employee")
    held_by(eva, a_role("Cashier", sale__view_sale=ON, sale__void_sale=APPROVAL, sale__take_payment=OFF))

    approvable = signed_in(eva)["approvable"]

    assert "sale.void_sale" in approvable
    assert "sale.take_payment" not in approvable


def test_what_a_role_of_the_business_never_lets_is_not_approvable(make_user):
    eva = make_user("saas:3", host=A.key, role="hub_employee")
    held_by(eva, a_role("Cashier", sale__view_sale=ON, sale__void_sale=OFF))

    assert "sale.void_sale" not in signed_in(eva)["approvable"]


# ── base.session.access: what a device follows to read its session again ──────────────────────────────────────────


def access_key(user, permissions: frozenset[str]) -> str:
    ctx = OperationContext(scope=A, actor=user, permissions=permissions, language="en")
    return get("base.session.access")(ctx, get("base.session.access").input()).key


def test_the_access_key_changes_with_what_the_role_gives(make_user):
    ana = make_user("ana")
    assert access_key(ana, permissions_of_role("hub_employee")) != access_key(ana, permissions_of_role("hub_manager"))


def test_the_same_permissions_give_the_same_key_to_anyone(make_user):
    ana, luis, employee = make_user("ana"), make_user("luis"), permissions_of_role("hub_employee")
    assert access_key(ana, employee) == access_key(luis, employee)
    assert access_key(ana, employee) == access_key(ana, frozenset(sorted(employee, reverse=True)))


def test_the_access_is_read_again_with_each_photo_of_erplora_com():
    from live.live_registry import live_registry

    from base.events import HUB_STATE_APPLIED

    assert "base.session.access" in live_registry.affected([HUB_STATE_APPLIED])


def test_the_access_key_changes_when_the_role_that_rules_is_renamed(make_user):
    eva = make_user("saas:3", host=A.key, role="hub_employee")
    role = a_role("Cashier", sale__view_sale=ON)
    held_by(eva, role)
    before = access_key(eva, access_for(eva, A))

    role.name = "Till"
    role.save()

    assert access_key(eva, access_for(eva, A)) != before


def test_the_access_key_changes_with_what_a_manager_may_approve(make_user):
    """What it grants stays the same: only whether a manager may approve the rest moves."""
    eva = make_user("saas:3", host=A.key, role="hub_employee")
    role = a_role("Cashier", sale__view_sale=ON, sale__void_sale=OFF)
    held_by(eva, role)
    granted, before = access_for(eva, A), access_key(eva, access_for(eva, A))

    role.states = {**role.states, "sale.void_sale": APPROVAL}
    role.save()

    assert access_for(eva, A) == granted
    assert access_key(eva, granted) != before
