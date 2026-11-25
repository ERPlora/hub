"""A role given while somebody else deletes it: two sessions of the business at once, with real row locks. Either the
deletion hears that somebody has the role, or the giving hears that the role is no longer there; never an error of the
database."""

import pytest
from live.context import OperationContext
from live.errors import OperationError
from live.operations import get as get_operation

from base.models import HubUser, Membership
from base.models.roles import BusinessRole
from base.permissions import access_for
from base.tenancy.tests.business import A, HUB_DB_COMMITTED, in_business_a
from base.tenancy.tests.concurrency import meanwhile, plan_with_room
from base.tests.roles import a_role

__all__ = ["in_business_a", "plan_with_room"]

# With room for both sessions at once: on Free's plan the second would queue for its turn, never at the role's lock.
pytestmark = [HUB_DB_COMMITTED, pytest.mark.usefixtures("plan_with_room")]


@pytest.fixture
def run(make_user):
    olga = make_user("saas:1", host=A.key, role=Membership.Role.OWNER)
    make_user("saas:3", host=A.key, role=Membership.Role.EMPLOYEE)

    def call(operation: str, **arguments):
        op = get_operation(operation)
        ctx = OperationContext(scope=A, actor=olga, permissions=access_for(olga, A))
        return op(ctx, op.input(**arguments))

    return call


def gives_it(sql: str) -> bool:
    return "base_hubuser" in sql and sql.lstrip().startswith(("UPDATE", "INSERT"))


def deletes_it(sql: str) -> bool:
    return sql.lstrip().startswith('DELETE FROM "base_businessrole"')


def test_a_role_deleted_while_it_is_being_given_hears_that_somebody_has_it(run):
    role = a_role()

    with meanwhile(gives_it, lambda: run("base.role.delete", role=str(role.pk))) as deleted:
        run("base.role.assign", person="saas:3", role=str(role.pk))

    assert isinstance(deleted[0], OperationError), repr(deleted[0])
    assert deleted[0].code == "base.role_in_use"
    assert HubUser.objects.get(username="saas:3").business_role == role


def test_a_role_given_while_it_is_being_deleted_hears_that_it_is_not_there(run):
    role = a_role()

    with meanwhile(deletes_it, lambda: run("base.role.assign", person="saas:3", role=str(role.pk))) as given:
        run("base.role.delete", role=str(role.pk))

    assert isinstance(given[0], OperationError), repr(given[0])
    assert given[0].code == "base.role_not_found"
    assert not BusinessRole.objects.exists()
    assert not HubUser.objects.filter(business_role__isnull=False).exists()
