"""``base.session.me`` with the real modules and roles: each role's menu, and so its «My apps», lists only the screens
it may open.

An employee has the apps of the floor (selling, the till, tables, kitchen, bookings, the agenda, customers, the time
clock…) and none of those that set the business up; the apps it does not open stay among its ``apps``, which other
screens read to know that an app is on (the till sells modifiers and menus).
"""

from live.context import OperationContext
from live.meta import module_configs
from live.operations import get

from base import home
from base.permissions import permissions_of_role
from base.schemas.sessions import SessionMeIn
from base.tenancy.tests.business import HUB_DB, A, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB

#: The apps that set the business up: whoever manages them opens them, never an employee.
SETUP_APPS = {"tax", "pricing", "modifier", "combo", "payment", "schedule", "verifactu", "printing", "website"}
FLOOR_APPS = {"sale", "cash_register", "table", "kitchen", "reservation", "appointment", "customer", "attendance"}


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
    assert menu["staff"] == ["/staff/members", "/staff/time-off", "/staff/schedules"]
    assert menu["flow"] == ["/flow/automations"]


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
        for config in home.shown_modules(demo_hub=False)
        if config.navigation
    }
    assert menu_of(make_user("olga"), "hub_owner") == every
    assert menu_of(make_user("adrian"), "hub_admin") == every
    assert every.keys() == {config.label for config in module_configs() if config.navigation}
