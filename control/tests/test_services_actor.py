"""Who runs control's commands: the platform, or one of its admins in the Hub admin, and the name a change is
recorded with."""

import pytest
from live.context import system_context
from live.errors import PermissionDenied

from base.registry import REGISTRY_SCOPE
from control.services import actor
from control.tests.conftest import as_actor, person

pytestmark = pytest.mark.django_db


def test_the_platform_and_its_admins_may():
    actor.platform_admin_only(system_context(REGISTRY_SCOPE))
    actor.platform_admin_only(as_actor(person("root", is_staff=True, is_superuser=True)))


@pytest.mark.parametrize("flags", [{"is_staff": True}, {}, {"is_superuser": True}])
def test_support_a_customer_or_a_superuser_who_is_no_staff_may_not(flags):
    with pytest.raises(PermissionDenied) as refused:
        actor.platform_admin_only(as_actor(person("someone", **flags)))

    assert refused.value.code == "base.internal_only"


def test_a_change_is_recorded_with_the_staff_members_name_or_username_or_the_platform():
    named = person("ana", first_name="Ana", last_name="García", is_staff=True, is_superuser=True)

    assert actor._who(as_actor(named)) == "Ana García"
    assert actor._who(as_actor(person("root", is_staff=True, is_superuser=True))) == "root"
    assert actor._who(system_context(REGISTRY_SCOPE)) == "system"
    assert actor._who(as_actor("x" * 200)) == "x" * 150
