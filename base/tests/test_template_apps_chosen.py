"""The apps a template or a copy turns on are the business's choice, as if turned on one by one in Apps (BASE-F31,
BASE-F18): turning one of them off never takes the others with it (BASE-F23). What a load brings only because an app
it turns on needs it still goes off with that app, and what was on before the load is left as it was."""

from live.operations import get

from base import activation
from base.catalog.verticals import template_apps
from base.models.activation import AppActivation
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.test_services_data import born, call, chosen, load, modules_on, with_max_apps

__all__ = ["born", "in_business_a", "load"]
pytestmark = HUB_DB


def along_said(ctx, app):
    """What the Apps screen asks before flipping ``app``'s switch: the apps that would go off with it."""
    op = get("base.app.list")
    rows = op(ctx, op.input()).model_dump(mode="json")["apps"]
    return next(row["along_said"] for row in rows if row["id"] == app)


def born_with_taxes():
    """Business A as its sign-up leaves it: Taxes on, not chosen, every other app off."""
    graph = activation.module_graph()
    AppActivation.objects.bulk_create(
        AppActivation(host=A.key, app=label, state=row.state, chosen=row.chosen)
        for label, row in activation.born(activation.born_apps("ES"), graph).items()
    )
    activation.forget(A.key)


def test_turning_off_online_bookings_keeps_the_agenda_the_services_and_the_hours_the_template_turned_on(born, load):
    load(born, template="hair_salon.es")

    assert along_said(born, "online_booking") == ""
    turned_off = call(born, "base.app.disable", app="online_booking")

    assert turned_off.along == []
    assert {"appointment", "schedule", "service"} <= modules_on()
    assert modules_on() == set(template_apps("hair_salon")) - {"online_booking"}


def test_every_app_a_template_turns_on_is_chosen_and_one_already_on_is_left_as_it_was(born, load):
    born_with_taxes()

    load(born, template="hair_salon.es")

    assert chosen() == set(template_apps("hair_salon")) - {"tax"}
    assert AppActivation.objects.get(host=A.key, app="tax").chosen is False


def test_what_comes_only_because_an_app_of_the_load_needs_it_still_goes_off_with_it(born, load):
    load(born, template="restaurant.es", apps=["reservation"])
    assert chosen() == {"reservation"}

    turned_off = call(born, "base.app.disable", app="reservation")

    assert {app.id for app in turned_off.along} == activation.needs(["reservation"], activation.module_graph()) - {"tax"}
    assert modules_on() == {"tax"}


def test_a_spanish_restaurant_on_the_free_plan_loads_its_template_and_still_turns_verifactu_on(born, load):
    """Free allows 20 chosen apps on erplora.com: the restaurant's (Taxes aside, on since the sign-up) and VeriFactu."""
    born_with_taxes()
    with_max_apps(A.key, 20)

    loaded = load(born, template="restaurant.es")
    call(born, "base.app.enable", app="verifactu")

    assert loaded.status == "complete"
    assert "verifactu" in modules_on()
