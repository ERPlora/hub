"""The Hub's own screens, as its help serves them (``base/platform_screens.py``): the pages of base the SPA opens, each
with the permission its page asks.
"""

import re

import pytest
from django.conf import settings
from live.operations import get

from base.platform_screens import SCREENS

FRONTEND = settings.BASE_DIR / "base" / "frontend"
ROUTE = re.compile(r"path: '([^']+)'")
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
