"""VeriFactu is mandatory in Spain, and the platform never turns it on by itself (hub#997, PLAN-HUB round 2026-11-07).

It says so in its ``LiveAppConfig`` (``mandatory``), which base reads without naming it: while a business of Spain (or
one without a country, a demo, in ERPlora's market) has it off, «Finish setting up your business» asks whoever runs it
to turn it on, leading to Apps; once on, that step goes and VeriFactu's own («Set up VeriFactu») follows. A business of
another country is never asked. VeriFactu binds the business to the AEAT until the end of the calendar year and needs
its authorisation, so the platform never turns it on at sign-up (``platform_turns_on``): its owner does.

Two real hubs, each with its own database: each reads its own business's country and its own apps.
"""

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import get

from apps.verifactu.tests.conftest import business_in
from apps.verifactu.tests.test_app_enable import verifactu_off
from base import activation
from base.schemas import SetupStatusIn
from base.tenancy import context
from base.tenancy.tests import hubs
from control.models import Hub

STEP = "base.mandatory.verifactu"


def admin(scope: Scope, language: str = "en") -> OperationContext:
    return OperationContext(scope=scope, actor="ana", permissions=frozenset({"*"}), language=language)


def checklist(scope: Scope, language: str = "en") -> dict[str, dict]:
    document = get("base.setup.status")(admin(scope, language), SetupStatusIn()).model_dump(mode="json")
    return {item["key"]: item for item in document["items"]}


def enable(scope: Scope, app: str) -> dict:
    op = get("base.app.enable")
    return op(admin(scope), op.input.model_validate({"app": app})).model_dump(mode="json")


def test_it_declares_spain_and_that_only_its_owner_turns_it_on():
    assert apps.get_app_config("verifactu").mandatory == {"countries": ["ES"], "platform_turns_on": False}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_business_of_spain_with_it_off_is_asked_to_turn_it_on_and_one_of_poland_is_not(hub_a, hub_b, no_test_fallback):
    business_in("PL", hub_a.slug)
    business_in("ES", hub_b.slug)
    of_a, of_b = Scope("host", hub_a.slug), Scope("host", hub_b.slug)

    with context.use_hub(hub_a):
        verifactu_off(hub_a.slug)
        assert STEP not in checklist(of_a)
    with context.use_hub(hub_b):
        verifactu_off(hub_b.slug)
        step = checklist(of_b, "es")[STEP]
        assert {k: step[k] for k in ("state", "level", "actionable", "route", "icon")} == {
            "state": "pending",
            "level": "functional",
            "actionable": True,
            "route": "/apps#all",
            "icon": "ion:list-outline",  # as «My apps» paints VeriFactu: its first menu entry's
        }
        assert (step["title"], step["description"]) == (
            "Activa VeriFactu",
            "Es obligatoria para los negocios de España.",
        )


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_once_on_the_step_goes_and_verifactus_own_follows_without_touching_the_other_hub(hub_a, hub_b, no_test_fallback):
    business_in("ES", hub_a.slug)
    # Its database has every app's tables, as one cloned from the template: turning VeriFactu on puts it on at once.
    Hub.objects.filter(pk=hub_a.pk).update(schema_apps={label: "0001_initial" for label in activation.module_graph()})
    of_a, of_b = Scope("host", hub_a.slug), Scope("host", hub_b.slug)  # b has no country: Spain too
    with context.use_hub(hub_b):
        verifactu_off(hub_b.slug)
    with context.use_hub(Hub.objects.get(pk=hub_a.pk)):
        verifactu_off(hub_a.slug)
        assert "verifactu.sending_route" not in checklist(of_a)

        enable(of_a, "verifactu")
        activation.forget(hub_a.slug)  # what the change does at its COMMIT, which the test's transaction never reaches
        assert activation.states_of(of_a)["verifactu"].on

        after = checklist(of_a)
        assert STEP not in after
        assert "verifactu.sending_route" in after
    with context.use_hub(hub_b):
        assert STEP in checklist(of_b)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_while_its_tables_are_being_made_it_is_not_on_yet_and_the_step_stays(hub_a, no_test_fallback):
    business_in("ES", hub_a.slug)
    of_a = Scope("host", hub_a.slug)
    with context.use_hub(hub_a):  # control knows of no table of its database: turning an app on makes them first
        verifactu_off(hub_a.slug)

        enable(of_a, "verifactu")
        activation.forget(hub_a.slug)  # what the change does at its COMMIT, which the test's transaction never reaches

        assert activation.states_of(of_a)["verifactu"].state == activation.CREATING
        assert STEP in checklist(of_a)
