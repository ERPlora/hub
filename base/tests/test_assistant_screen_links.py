"""The screens the assistant may link: every screen of the platform the person may open, each tab by its own name, beside
the menus of the apps that are on. The roles of the business are linked on Employees › Roles, never on Staff's roles, the
job titles of that app."""

import re

import pytest
from live.operations import get

from base.models import Membership
from base.permissions import permissions_of_role
from base.platform_screens import SCREENS
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.fake_gateway import gateway
from base.tests.test_services_assistant import ASK, ctx

__all__ = ["gateway", "in_business_a"]

pytestmark = HUB_DB

OWNER = permissions_of_role(Membership.Role.OWNER)
EMPLOYEE = permissions_of_role(Membership.Role.EMPLOYEE)
#: A screen the instructions let the model link, one per line: «- [its name](its path)».
LINK = re.compile(r"^- \[(?P<name>[^\]]+)\]\((?P<path>/[^)]*)\)$", re.MULTILINE)


def linked(permissions, language: str) -> dict[str, str]:
    """The screens the assistant may link for whoever holds ``permissions``, by path, as its instructions name them."""
    op = get("base.assistant.turn")
    turn = op(ctx(permissions, language=language), op.input.model_validate({"messages": [ASK]}))
    return {match["path"]: match["name"] for match in LINK.finditer(turn.model_dump()["instructions"])}


@pytest.mark.parametrize(
    "language, roles, staff",
    [("es", "Empleados › Roles", "Personal › Roles"), ("en", "Employees › Roles", "Staff › Roles")],
)
def test_the_roles_of_the_business_are_linked_on_employees_and_staffs_job_titles_on_staff(language, roles, staff):
    links = linked(OWNER, language)

    assert (links.get("/employees#roles"), links.get("/staff/roles")) == (roles, staff)


@pytest.mark.parametrize("permissions", [OWNER, EMPLOYEE], ids=["owner", "employee"])
def test_every_screen_of_the_platform_the_person_may_open_may_be_linked(permissions):
    asking = ctx(permissions)
    may_open = {tab.path for tab in SCREENS if ":" not in tab.path and asking.has(tab.permission)}

    assert may_open - set(linked(permissions, "es")) == set()
