"""Services on the Home (PLAN-HUB round 2026-10-21; FIX-SERVICE-SETUP-HOOKS): base's own query brings the old module's
item «Your service catalogue» (module.json `setup`, services#26), important, pending until one offered service can be
charged (its tax category alive), to whoever adds services, leading to the list of services. Every change of it records
an event it is refreshed on, and a change in hub B re-runs B's Home only; with Services off the Home does not ask.

base and service run for real: the step comes from ServiceConfig through base's own query, as the person.
"""

import json

import psycopg
import pytest
from live.context import OperationContext, Scope
from live.live_registry import live_registry
from live.meta import all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.service.models import Service
from apps.service.tests.conftest import A, B, make_service, make_tax
from base.schemas import SetupStatusIn

STEP = "service.catalog"
TAX = "test.service"
WAIT = 1.0
QUIET = 0.3


def person(
    role: str = "hub_owner", scope: Scope = A, language: str = "en", permissions: set[str] | None = None
) -> OperationContext:
    """Whoever reads the Home: the role's permissions on ``scope`` (``permissions`` replaces them), in ``language``."""
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor="tester", permissions=permissions, language=language)


def step(ctx=None) -> dict | None:
    """Services' step of «Finish setting up your business» for the person of ``ctx`` (``None``: not told)."""
    items = get("base.setup.status")(ctx or person(), SetupStatusIn()).model_dump(mode="json")["items"]
    found = [item for item in items if item["app"] == "service"]
    assert len(found) <= 1, found
    return found[0] if found else None


def run(name: str, data: dict, ctx: OperationContext | None = None):
    op = get(name)
    return op(ctx or person("hub_admin"), op.input.model_validate(data))


@pytest.fixture
def tax(db):
    return make_tax(TAX)


@pytest.mark.django_db
def test_a_hub_without_services_has_your_service_catalogue_pending_and_it_leads_to_the_services():
    item = step()
    assert {name: item[name] for name in ("key", "state", "level", "required", "actionable", "route", "order", "icon")} == {
        "key": STEP,
        "state": "pending",
        "level": "functional",
        "required": True,
        "actionable": True,
        "route": "/service/services",
        "order": 31,
        "icon": "ion:briefcase-outline",
    }
    assert (item["title"], item["description"]) == (
        "Your service catalogue",
        "Add the services you sell, with their price and duration.",
    )


@pytest.mark.django_db
def test_in_spanish_it_says_the_old_words():
    item = step(person(language="es"))
    assert (item["title"], item["description"]) == (
        "Tu catálogo de servicios",
        "Añade los servicios que vendes, con su precio y su duración.",
    )


@pytest.mark.django_db
def test_one_service_that_can_be_charged_ticks_it(tax):
    make_service("Haircut", tax=tax)
    assert step()["state"] == "done"


@pytest.mark.django_db
def test_an_archived_service_or_one_whose_tax_category_is_gone_cannot_be_charged(tax):
    # The old module's `sellable_services`: offered (not archived) and with a live tax category, or the till refuses it.
    gone = make_tax("test.gone", "Gone", is_active=False)
    make_service("Haircut", tax=tax, is_active=False)
    make_service("Colour", tax=gone)
    assert step()["state"] == "pending"


@pytest.mark.django_db
def test_every_service_archived_puts_it_back_to_pending(tax):
    haircut = make_service("Haircut", tax=tax)
    assert step()["state"] == "done"
    Service.objects.filter(pk=haircut.pk).update(is_active=False)
    assert step()["state"] == "pending"


@pytest.mark.django_db
def test_whoever_adds_services_is_told_and_who_only_reads_them_is_not():
    # Important, never ⛔: who cannot add a service is not told (base's rule). The employee adds services (the old
    # module gave it to the cashier too), so the employee is told.
    assert step(person("hub_manager"))["state"] == "pending"
    assert step(person("hub_employee"))["state"] == "pending"
    reader = permissions_for_role(all_live_app_configs(), "hub_employee") - {"service.add_service"}
    assert step(person(permissions=reader)) is None


@pytest.mark.django_db
def test_with_services_off_the_home_does_not_ask_for_its_catalogue():
    # base brings only the steps of the modules on in the scope: Services off (after the apps that need it), no step.
    administrator = OperationContext(scope=A, actor="ana", permissions=frozenset({"*"}))
    for app in ("online_booking", "appointment", "service"):
        run("base.app.disable", {"app": app}, administrator)
    assert step() is None
    assert step(person(scope=B))["state"] == "pending"


def add_one(tax, service):
    run("service.service.create", {"name": "Beard trim", "tax_category_key": TAX, "price": 1200})


def add_many(tax, service):
    run(
        "service.service.bulk_create",
        {"services": [{"name": "Wash", "tax_category_key": TAX}, {"name": "Dry", "tax_category_key": TAX}]},
    )


def retax(tax, service):
    run("service.service.update", {"id": str(service.id), "tax_category_key": TAX})


def archive(tax, service):
    run("service.service.archive", {"id": str(service.id)})


def restore(tax, service):
    run("service.service.restore", {"id": str(service.id)})


#: Each event of the step's ``refresh_on`` → the change that records it and the state it leaves the step in.
CHANGES = {
    "service.service.created": [(add_one, "done"), (add_many, "done")],
    "service.service.updated": [(retax, "done")],
    "service.service.archived": [(archive, "pending")],
    "service.service.restored": [(restore, "done")],
}


def start_from(change, tax):
    """The one service a change acts on, so that the change is what moves the step: a sellable one to archive, an
    archived one to restore, one whose tax category is gone to give a live one, none to add."""
    if change is archive:
        return make_service("Haircut", tax=tax)
    if change is restore:
        return make_service("Haircut", tax=tax, is_active=False)
    return make_service("Haircut", tax=make_tax("test.gone", "Gone", is_active=False))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event,change,state",
    [(event, change, state) for event, cases in CHANGES.items() for change, state in cases],
    ids=lambda value: getattr(value, "__name__", value),
)
def test_each_change_of_the_step_records_an_event_that_refreshes_it(tax, event, change, state):
    service = start_from(change, tax)
    before = step()["state"]
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    change(tax, service)
    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert (before, step()["state"]) == ("done" if state == "pending" else "pending", state)
    assert recorded & set(service_app().setup[0].refresh_on) == {event}


def service_app():
    from django.apps import apps

    return apps.get_app_config("service")


def test_the_step_is_refreshed_on_nothing_else():
    assert set(service_app().setup[0].refresh_on) == set(CHANGES)


def test_base_re_runs_the_home_on_them():
    assert set(CHANGES) <= set(live_registry.subscribable["base.setup.status"])


# ── Two hubs ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_a_service_added_in_hub_b_re_runs_the_home_of_b_and_tells_a_nothing(listen):
    make_tax(TAX)
    on_a, on_b = listen(A), listen(B)
    run("service.service.create", {"name": "Haircut", "tax_category_key": TAX, "price": 1500}, person("hub_admin", B))

    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert "base.setup.status" in live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
