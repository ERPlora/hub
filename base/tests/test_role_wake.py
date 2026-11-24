"""A change of a role of the business reaches every open device of that business after its COMMIT, and of no other
(BASE-F128): what a person may do decides what every live query gives them, so all of them run again («*»)."""

import pytest
from live.context import OperationContext
from live.errors import OperationError
from live.operations import get as get_operation

from base import events
from base.models import Membership
from base.models.roles import BusinessRole
from base.permissions import access_for
from base.roles import ON
from base.tenancy.tests.business import A, B, HUB_DB_COMMITTED, in_business_a
from base.tests.test_hub_state_wake import heard, listening

__all__ = ["in_business_a", "listening"]

pytestmark = HUB_DB_COMMITTED


@pytest.fixture
def ctx(make_user):
    olga = make_user("saas:1", host=A.key, role=Membership.Role.OWNER)
    return OperationContext(scope=A, actor=olga, permissions=access_for(olga, A))


@pytest.fixture
def cashier():
    return BusinessRole.objects.create(name="Cashier", origin=Membership.Role.EMPLOYEE, states={"sale.view_sale": ON})


def run(ctx, operation: str, /, **arguments):
    op = get_operation(operation)
    return op(ctx, op.input(**arguments))


def test_a_change_of_what_a_role_allows_wakes_every_open_device_of_its_business(ctx, cashier, listening):
    here, there = listening(A), listening(B)

    run(ctx, "base.role.update", role=str(cashier.pk), states={"sale.view_sale": "off"})

    assert {"*", events.ROLE_UPDATED} <= heard(here)
    assert heard(there, timeout=0.5) == set()


def test_a_refused_change_wakes_nobody(ctx, cashier, listening):
    here = listening(A)

    with pytest.raises(OperationError):
        run(ctx, "base.role.update", role=str(cashier.pk), states={"base.own_business": "on"})

    assert heard(here, timeout=0.5) == set()


def test_a_role_made_or_deleted_reaches_the_list_of_roles_of_its_business(ctx, cashier, listening):
    here, there = listening(A), listening(B)

    run(ctx, "base.role.create", based_on="hub_employee", name="Till")
    assert events.ROLE_CREATED in heard(here)
    run(ctx, "base.role.delete", role=str(cashier.pk))
    assert events.ROLE_DELETED in heard(here)

    assert heard(there, timeout=0.5) == set()
