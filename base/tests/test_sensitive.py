"""The data permissions of base: which sensitive data each role sees.

A field of a schema marked with one of these (``base.sensitive``) reaches only whoever holds its permission
(``live.sensitive``): the rest receive it as null, by every door. The owner, an administrator and a manager hold the four;
an employee only the customers' contact details, which serving them needs.
"""

import pytest
from django.apps import apps
from live.sensitive import REQUIRES

from base import sensitive
from base.models import Membership
from base.permissions import permissions_of_role

DATA_PERMISSIONS = {
    "base.view_costs",
    "base.view_customer_contact",
    "base.view_team_contact",
    "base.view_business_totals",
}


def test_base_declares_the_four_data_permissions():
    assert DATA_PERMISSIONS <= set(apps.get_app_config("base").permissions)
    assert sensitive.DATA_PERMISSIONS == DATA_PERMISSIONS


@pytest.mark.parametrize(
    ("mark", "permission"),
    [
        (sensitive.COSTS, "base.view_costs"),
        (sensitive.CUSTOMER_CONTACT, "base.view_customer_contact"),
        (sensitive.TEAM_CONTACT, "base.view_team_contact"),
        (sensitive.BUSINESS_TOTALS, "base.view_business_totals"),
    ],
)
def test_each_mark_requires_its_permission(mark, permission):
    assert mark == {REQUIRES: permission}


@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER])
def test_who_runs_the_business_or_manages_it_sees_every_piece_of_data(role):
    assert DATA_PERMISSIONS <= permissions_of_role(role)


def test_an_employee_sees_only_the_customers_contact_details():
    assert permissions_of_role(Membership.Role.EMPLOYEE) & DATA_PERMISSIONS == {"base.view_customer_contact"}
