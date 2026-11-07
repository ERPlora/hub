"""VeriFactu does not go on outside Spain (VERIFACTU-F01, hub#694).

VeriFactu binds the taxpayers of Spain alone and, for a business registered elsewhere, seals and sends nothing
(``test_outside_spain``). The platform's ``base.app.enable`` asks the app's ``can_enable`` (``base.activation.veto``):
outside Spain it is 409 ``base.app_vetoed`` with the reason in the reader's language and the app stays off, and
``base.app.list`` says so beforehand. A business in Spain, or without a country (a demo, in ERPlora's market), turns it
on. One already on outside Spain stays as it is and can go off (``test_app_disable``). Each hub reads its own business's
country.

A template of the catalogue never turns it on, in Spain either (PLAN-HUB round 2026-11-07, hub#998): VeriFactu binds the
business to the AEAT until the end of the calendar year and never goes off once on (VERIFACTU-F32), so its owner turns it
on, from Apps.
"""

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import get

from apps.verifactu.queries import VERIFACTU
from apps.verifactu.tests.conftest import A, business_in
from base import activation, events, services
from base import blueprint
from base.models import AppActivation
from base.tenancy import context
from base.tenancy.tests import hubs
from base.tests.test_services_data import born, call, load, modules_on  # noqa: F401 (fixtures)

ONLY_IN_SPAIN = "VeriFactu is only for businesses in Spain."
ONLY_IN_SPAIN_ES = "VeriFactu solo es para negocios de España."


def admin(scope: Scope = A, language: str = "en") -> OperationContext:
    return OperationContext(scope=scope, actor="ana", permissions=frozenset({"*"}), language=language)


def enable(context_: OperationContext | None = None, app: str = "verifactu") -> dict:
    op = get("base.app.enable")
    return op(context_ or admin(), op.input.model_validate({"app": app})).model_dump(mode="json")


def verifactu_off(host: str = "a") -> None:
    """Every app of ``host`` as a business that never turned VeriFactu nor what it needs on."""
    AppActivation.objects.filter(host=host).delete()
    AppActivation.objects.bulk_create(
        AppActivation(host=host, app=label, state=activation.OFF, chosen=False) for label in activation.module_graph()
    )
    activation.forget(host)


def row_of(language: str = "en", scope: Scope = A) -> dict:
    op = get("base.app.list")
    document = op(admin(scope, language), op.input()).model_dump(mode="json")
    return {row["id"]: row for row in document["apps"]}["verifactu"]


@pytest.mark.django_db
@pytest.mark.parametrize("country", ["PL", "FR", "PT"])
def test_outside_spain_it_is_refused_with_the_reason_and_nothing_goes_on(country):
    business_in(country)
    verifactu_off()
    before = OutboxEvent.objects.filter(name=events.APP_ENABLED).count()

    with pytest.raises(Conflict) as refused:
        enable()

    error = refused.value.envelope()["error"]
    assert (refused.value.status, error["code"], error["app"]) == (409, "base.app_vetoed", "verifactu")
    assert refused.value.message == ONLY_IN_SPAIN
    states = activation.states_of(A)
    assert not any(states[label].wanted for label in ("verifactu", "invoice", "tax", "sale", "customer"))
    assert OutboxEvent.objects.filter(name=events.APP_ENABLED).count() == before
    assert apps.get_app_config("verifactu").can_enable(admin()) == ONLY_IN_SPAIN


@pytest.mark.django_db
def test_the_reason_is_in_the_language_of_whoever_turns_it_on():
    business_in("PL")
    verifactu_off()

    with pytest.raises(Conflict) as refused:
        enable(admin(language="es"))

    assert refused.value.message == ONLY_IN_SPAIN_ES


@pytest.mark.django_db
@pytest.mark.parametrize("country", ["ES", "es", ""])
def test_in_spain_or_without_a_country_it_goes_on(country):
    business_in(country)
    verifactu_off()

    assert apps.get_app_config("verifactu").can_enable(admin()) is None
    assert enable()["state"] == "on"
    assert activation.states_of(A)["verifactu"].on


@pytest.mark.django_db
def test_outside_spain_the_list_says_it_is_not_available_with_the_reason():
    business_in("PL")
    verifactu_off()

    row = row_of()

    assert (row["state"], row["refusal"]) == ("off", ONLY_IN_SPAIN)
    assert row_of("es")["refusal"] == ONLY_IN_SPAIN_ES


@pytest.mark.django_db
@pytest.mark.parametrize("country", ["ES", ""])
def test_in_spain_the_list_offers_it(country):
    business_in(country)
    verifactu_off()

    row = row_of()

    assert (row["state"], row["refusal"]) == ("off", None)


@pytest.mark.django_db
def test_outside_spain_what_verifactu_needs_goes_on_all_the_same():
    business_in("PL")
    verifactu_off()

    assert enable(app="invoice")["state"] == "on"
    assert not activation.states_of(A)["verifactu"].wanted


@pytest.mark.django_db
def test_a_blueprint_outside_spain_leaves_it_off_with_the_reason_and_turns_on_the_rest():
    """A blueprint turns on its apps through ``base.app.enable``: one that refuses stays off, the rest load."""
    business_in("PL")
    verifactu_off()

    refused = services._turn_on_listed(admin(), ["task", "verifactu"], set())

    assert refused == {"verifactu": ONLY_IN_SPAIN}
    states = activation.states_of(A)
    assert states["task"].on
    assert not states["verifactu"].wanted


@pytest.mark.django_db
@pytest.mark.parametrize("key", [seed.key for seed in blueprint.catalog()])
def test_a_template_in_spain_leaves_verifactu_off_for_the_home_to_ask_and_turns_on_the_rest(born, load, key):  # noqa: F811
    """The review does not announce it and the load leaves it off, so «Finish setting up your business» asks its owner
    to turn it on (hub#997); everything else the template lists goes on, what VeriFactu needs included (hub#998)."""
    business_in("ES", slug="c")

    review = call(born, "base.blueprint.inspect", template=key)
    loaded = load(born, template=key)

    on = modules_on()
    turns_on = {app.id for app in review.apps if app.status == "turns_on"}
    assert VERIFACTU not in {app.id for app in review.apps}
    assert VERIFACTU not in on
    assert not activation.states_of(Scope("host", "c"))[VERIFACTU].wanted
    assert set(apps.get_app_config(VERIFACTU).requires) <= turns_on <= on
    assert loaded.status == "complete"
    checklist = {item.key: item.state for item in call(born, "base.setup.status").items}
    assert checklist[f"base.mandatory.{VERIFACTU}"] == "pending"


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_each_hub_reads_its_own_business_country(hub_a, hub_b, poland_and_spain):
    of_a, of_b = poland_and_spain

    with context.use_hub(hub_a):
        verifactu_off(hub_a.slug)
        with pytest.raises(Conflict) as refused:
            enable(admin(of_a))
        assert refused.value.message == ONLY_IN_SPAIN
        assert row_of(scope=of_a)["refusal"] == ONLY_IN_SPAIN
    with context.use_hub(hub_b):
        verifactu_off(hub_b.slug)
        assert row_of(scope=of_b)["refusal"] is None
        assert enable(admin(of_b))["state"] in ("on", "creating")
        assert activation.states_of(of_b)["verifactu"].wanted
