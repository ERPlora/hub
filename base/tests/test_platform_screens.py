"""The Hub's own screens, as its help serves them (``base/platform_screens.py``): the pages of base the SPA opens, each
with the permission its page asks.
"""

import re

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.operations import get

from base.models import Membership
from base.permissions import permissions_of_role
from base.platform_screens import ROLES, SCREENS, permission_of
from base.queries import app_help

FRONTEND = settings.BASE_DIR / "base" / "frontend"
ROUTE = re.compile(r"path: '([^']+)'")
ROUTE_META = re.compile(r"path: '([^']+)',\n(?:(?!path: ).)*?meta: \{([^}]*)\}", re.DOTALL)
HASH = re.compile(r"'(#[a-z]+)'")
SETTINGS_TAB = re.compile(r"\{ id: '(\w+)'.*permission: '([\w.]+)' \}")

#: The operation each page reads to open (a tab of a page, the tab's own). Settings › General and Business ask no more
#: than the page itself, and Settings › Printing reads nothing: the test of the tabs of Settings checks them.
READS = {
    "home": "base.widget.list",
    "home_activity": "base.widget.list",
    "employees": "base.person.list",
    "employees_roles": "base.role.list",
    "role": "base.role.detail",
    "employees_apikeys": "base.api_key.list",
    "employees_approvals": "base.approval.list",
    "person": "base.person.detail",
    "files": "base.file.list",
    "apps": "base.app.list",
    "system_usage": "base.plan.usage",
    "system_updates": "base.system.status",
    "system_events": "base.failed_event.list",
    "system_logs": "base.event.list",
    "settings_data": "base.blueprint.list",
    "profile": "base.profile.get",
}


def source(path: str) -> str:
    return (FRONTEND / path).read_text(encoding="utf-8")


def test_each_screen_has_an_id_and_an_address_of_its_own():
    assert len({screen.id for screen in SCREENS}) == len({screen.path for screen in SCREENS}) == len(SCREENS)


def test_each_address_is_a_route_of_the_platform_with_its_parameters_unread():
    routes = set(ROUTE.findall(source("routes.ts")))
    assert [screen.path for screen in SCREENS if screen.path.partition("#")[0] not in routes] == []


def test_the_routes_that_offer_the_help_are_those_with_a_screen_in_it():
    routes = dict(ROUTE_META.findall(source("routes.ts")))
    assert {screen.path.partition("#")[0] for screen in SCREENS} == {
        path for path, meta in routes.items() if "help: true" in meta
    }


@pytest.mark.parametrize(
    ("page", "file"), [("/", "pages/HomePage.vue"), ("/employees", "lib/people.ts"), ("/system", "lib/system.ts")]
)
def test_the_tabs_of_a_page_are_those_it_writes_in_its_address(page, file):
    hashes = {f"#{screen.path.partition('#')[2]}" for screen in SCREENS if screen.path.startswith(f"{page}#")}
    assert hashes
    assert hashes <= set(HASH.findall(source(file)))


def test_the_tabs_of_settings_are_all_of_them_each_for_whoever_has_the_tab():
    tabs = SETTINGS_TAB.findall(source("lib/settings-tabs.ts"))
    assert tabs
    assert {screen.path: screen.permission for screen in SCREENS if screen.path.startswith("/settings")} == {
        f"/settings#{tab}": permission for tab, permission in tabs
    }


@pytest.mark.parametrize("screen", [screen for screen in SCREENS if screen.id in READS], ids=lambda screen: screen.id)
def test_a_screen_is_for_whoever_the_operation_it_reads_lets_in(screen):
    assert screen.permission == get(READS[screen.id]).permission


def test_every_screen_but_the_tabs_of_settings_that_read_nothing_else_names_its_operation():
    assert {screen.id for screen in SCREENS} - set(READS) == {"settings_general", "settings_business", "settings_printing"}
    assert set(READS) <= {screen.id for screen in SCREENS}


@pytest.mark.parametrize(
    ("role", "above"),
    [
        ("accountancy firm", [*Membership.Role]),
        ("employee", [*Membership.Role]),
        ("manager", [Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER]),
        ("administrator", [Membership.Role.OWNER, Membership.Role.ADMIN]),
        ("owner", [Membership.Role.OWNER]),
    ],
)
def test_what_a_task_of_a_role_asks_is_what_that_role_and_those_above_it_hold(role, above):
    with translation.override("en"):
        assert [r for r in Membership.Role if permission_of((role,)) in permissions_of_role(r)] == above


def test_every_role_of_the_business_is_one_a_manual_may_name():
    assert len(ROLES) == len(Membership.Role)


@pytest.mark.parametrize(
    ("actors", "permission"),
    [
        (("owner", "administrator", "manager", "employee"), "base.view_home"),
        (("administrator", "owner"), "base.administer_hub"),
        (("owner", "administrator", "ERPlora's support staff"), "base.administer_hub"),
        (("system",), "base.view_home"),
        ((), "base.view_home"),
    ],
)
def test_a_task_of_several_asks_what_the_least_of_its_roles_holds_and_one_of_no_role_is_anyone_s(actors, permission):
    with translation.override("en"):
        assert permission_of(actors) == permission


def test_the_manual_asks_the_same_of_a_person_for_a_task_in_every_language():
    def asked(language: str) -> dict[str, str]:
        served, read = app_help.help_of(apps.get_app_config("base"), language)
        assert served == language
        with translation.override(language):
            return {flow.id: permission_of(read.actors[flow.id]) for flow in read.flows}

    by_language = {language: asked(language) for language, _name in settings.LANGUAGES}
    assert by_language["es"]
    assert [language for language, read in by_language.items() if read != by_language["es"]] == []
