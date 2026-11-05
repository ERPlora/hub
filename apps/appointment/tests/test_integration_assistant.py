"""Appointments with the platform's assistant (hub#835): the card of a write of Citas that books services says each
service by its name, as the Diary does («Servicios: Corte de pelo, Tinte»), never «1 elemento» nor by its id. A
booking's services are lines that carry only their record (``[{"service_id": …}]``): the server names each one as
Services' read answers it to the person asking (the mark ``A_SERVICE``) and marks the list ``named``, so the screen
says them one after another (live.assistant ``NAMED``; @erplora/ui ``fieldText``). A mark alone is not enough
(base.E009 only checks the read exists): each write is checked here against the real name."""

import json

import pytest
from live.assistant import NAMED
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get, registry

from base import assistant
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID, list_field

from .conftest import make_service

#: The writes of Citas the assistant runs whose data carry the services of a booking, each a line of its own.
BOOKS_SERVICES = {
    "appointment.appointment.bulk_create",
    "appointment.appointment.create",
    "appointment.appointment.reschedule",
    "appointment.appointment.update",
    "appointment.recurring.create",
    "appointment.recurring.update",
}


@pytest.fixture
def no_fallback(monkeypatch):
    """As production: without ``use_hub`` a hub's model fails, nothing falls back on the shared database."""
    monkeypatch.setattr(context, "_test_fallback", None)


def person(hub, language: str, without: frozenset = frozenset()) -> OperationContext:
    """The business's admin in ``hub``, asking in ``language``, lacking the permissions ``without``."""
    return OperationContext(
        scope=Scope("host", hub.slug),
        actor="tester",
        permissions=permissions_for_role(all_live_app_configs(), "hub_admin") - without,
        language=language,
    )


def services_of(write: str, ids: list, ctx: OperationContext) -> dict:
    card = assistant.card(get(write), {"services": [{"service_id": str(id_)} for id_ in ids]}, ctx.language, ctx)
    assert not AN_ID.search(json.dumps(card, ensure_ascii=False)), write
    return list_field(card, "services")


def test_every_write_of_citas_that_books_services_is_listed_here():
    """Positive control of the tests below: a new write of Citas with a booking's services comes in here."""
    found = set()
    for name, op in registry.items():
        if op.app_label != "appointment" or op.kind != "command" or not assistant.is_tool(op):
            continue
        schema = op.input.model_json_schema()
        services = assistant._resolved(schema.get("properties", {}).get("services", {}), schema.get("$defs", {}))
        line = assistant._resolved(services.get("items", {}), schema.get("$defs", {}))
        if "service_id" in line.get("properties", {}):
            found.add(name)
    assert found == BOOKS_SERVICES


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("write", sorted(BOOKS_SERVICES))
def test_the_card_names_each_service_a_write_books(write, language, hub_a, no_fallback):
    """What Lucía asked for, a cut and a colour: the card says both by their names, in the person's language."""
    with use_hub(hub_a):
        cut, colour = make_service("Corte de pelo"), make_service("Tinte", duration=60)
        shown = services_of(write, [cut.id, colour.id], person(hub_a, language))
    assert shown["value"] == [{"service_id": "Corte de pelo"}, {"service_id": "Tinte"}]
    assert (shown["kind"], shown.get(NAMED)) == ("list", True)
    assert shown["label"] == {"es": "Servicios", "en": "Services"}[language]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_name_the_model_writes_as_null_beside_the_id_still_names_the_service(hub_a, no_fallback):
    """A model writes the name it does not give as null (``{"service_id": …, "service": null}``): the line still carries
    only its service, and the card names it."""
    with use_hub(hub_a):
        cut = make_service("Corte de pelo")
        booking = {"services": [{"service_id": str(cut.id), "service": None}]}
        card = assistant.card(get("appointment.appointment.create"), booking, "es", person(hub_a, "es"))
        shown = list_field(card, "services")
    assert (shown["value"], shown.get(NAMED)) == ([{"service_id": "Corte de pelo", "service": None}], True)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_service_the_person_may_not_see_is_left_out_never_by_its_id(language, hub_a, no_fallback):
    """Whoever may not read Services sees how many services the booking carries, never which by an id."""
    with use_hub(hub_a):
        cut = make_service("Corte de pelo")
        blind = person(hub_a, language, without=frozenset({get("service.service.get").permission}))
        shown = services_of("appointment.appointment.create", [cut.id], blind)
    assert (shown["value"], shown.get(NAMED)) == ([{}], True)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_service_of_another_business_is_never_named(hub_a, hub_b, no_fallback):
    """A service of business B, sent to a card of business A: A's card reads nothing of B's."""
    with use_hub(hub_b):
        theirs = make_service("Corte de B")
    with use_hub(hub_a):
        ours = make_service("Corte de pelo")
        shown = services_of("appointment.appointment.create", [ours.id, theirs.id], person(hub_a, "es"))
    assert shown["value"] == [{"service_id": "Corte de pelo"}, {}]
