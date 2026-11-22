"""The root conftest's businesses ``hub_a`` and ``hub_b`` are what a sign-up leaves: control's row lists the apps their
database already has (``Hub.schema_apps``), so turning one of them on answers «on» at once, never «creating»."""

import pytest
from live.context import OperationContext, Scope
from live.operations import get

from base import activation
from base.models.activation import AppActivation
from base.tenancy import migrator
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = [pytest.mark.django_db(databases=hubs.HUB_DATABASES)]

#: An app every template carries that nothing vetoes and whose requirements are on in both businesses.
APP = "task"


@pytest.fixture(params=["hub_a", "hub_b"])
def business(request):
    return request.getfixturevalue(request.param)


def turn_on(hub, app: str) -> str:
    owner = OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=frozenset({"*"}))
    enable = get("base.app.enable")
    return enable(owner, enable.input.model_validate({"app": app})).state


def test_an_app_the_database_has_goes_on_at_once(business):
    with use_hub(business):
        AppActivation.objects.filter(host=business.slug, app=APP).update(state=activation.OFF)
        activation.forget(business.slug)

        assert turn_on(business, APP) == activation.ON
        assert activation.states_of(Scope("host", business.slug))[APP].on


def test_its_row_is_not_behind_the_code(business):
    assert APP in migrator.portable_apps()
    assert not migrator.is_behind(business)
