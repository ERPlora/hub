"""What a service costs the business reaches only whoever sees the costs (``base.view_costs``), as a product's does
(BASE-F119, SERVICE-F01, SERVICE-F02 and SERVICE-F10): an employee reads the services with the cost empty, by the route
and by the assistant, and adds a service without one; a cost they send is refused as an operation they may not run."""

import json

import pytest
from live import assistant as shared
from live.errors import PermissionDenied
from live.operations import get as operation

from apps.flow.tests.test_api import get
from apps.service.models import Service
from apps.service.schemas import ServiceIn, ServicePatchIn
from base.sensitive import VIEW_COSTS

from .conftest import A, HUB_DB, ctx_for, make_service, make_tax

pytestmark = HUB_DB


@pytest.fixture
def haircut(db):
    return make_service("Haircut", tax=make_tax(), price=2000, cost=700)


@pytest.fixture
def as_role(client, make_user):
    def login(role: str):
        client.force_login(make_user(role, host=A.key, role=role))
        return client

    return login


@pytest.mark.parametrize(("role", "cost"), [("hub_employee", None), ("hub_manager", 700)])
def test_the_service_list_and_its_detail_carry_the_cost_only_to_who_sees_the_costs(haircut, as_role, role, cost):
    client = as_role(role)
    listed = get(client, "/service/services")
    detail = get(client, "/service/services/detail", id=str(haircut.id))
    assert [listed.status_code, detail.status_code] == [200, 200]
    assert [row["cost"] for row in listed.json()["rows"]] == [cost]
    assert detail.json()["cost"] == cost


@pytest.mark.parametrize(("role", "cost"), [("hub_employee", None), ("hub_manager", 700)])
def test_the_assistant_answers_the_cost_only_to_who_sees_the_costs(haircut, role, cost):
    outcome = shared.run_tool(ctx_for(role), operation("service.service.get"), json.dumps({"service": "Haircut"}))
    assert outcome.outcome == "ok", outcome.content
    assert json.loads(outcome.content)["cost"] == cost


def test_an_employee_adds_a_service_without_a_cost_and_is_refused_one_with_it(haircut):
    employee = ctx_for("hub_employee")
    tax = haircut.tax_category.key
    with pytest.raises(PermissionDenied):
        operation("service.service.create")(employee, ServiceIn(name="Colour", tax_category_key=tax, cost=900))
    assert not Service.objects.filter(name="Colour").exists()
    operation("service.service.create")(employee, ServiceIn(name="Colour", tax_category_key=tax))
    assert Service.objects.get(name="Colour").cost == 0


def test_changing_the_cost_is_refused_to_who_does_not_see_the_costs_and_kept_for_who_does(haircut):
    editor = ctx_for(permissions={"service.change_service", "service.view_service"})
    with pytest.raises(PermissionDenied):
        operation("service.service.update")(editor, ServicePatchIn(id=haircut.id, cost=10))
    operation("service.service.update")(ctx_for(permissions={*editor.permissions, VIEW_COSTS}), ServicePatchIn(id=haircut.id, cost=10))
    assert Service.objects.get(pk=haircut.pk).cost == 10
