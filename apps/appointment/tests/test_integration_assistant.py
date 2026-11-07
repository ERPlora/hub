"""Appointments with the platform's assistant (hub#835): the card of a write of Citas that books services says each
service by its name, as the Diary does («Servicios: Corte de pelo, Tinte»), never «1 elemento» nor by its id. A
booking's services are lines that carry only their record (``[{"service_id": …}]``): the server names each one as
Services' read answers it to the person asking (the mark ``A_SERVICE``) and marks the list ``named``, so the screen
says them one after another (live.assistant ``NAMED``; @erplora/ui ``fieldText``). With no id, the assistant sends the
service as a person says it (``[{"service": "Tinte"}]``): Citas marks that text a name (``name_of``, hub#860), so the
card says it too, and beside the id it says the service the booking takes. A mark alone is not enough (base.E009 and
base.E014 only check its shape): each write is checked here against the real name."""

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
from base.tests.test_assistant import technical_names
from base.tests.test_assistant_card_values import AN_ID, list_field

from .conftest import make_service
from .test_i18n import own_catalogue

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
    only its service, and the card names it. The name beside its record is left out, null or not (hub#860)."""
    with use_hub(hub_a):
        cut = make_service("Corte de pelo")
        booking = {"services": [{"service_id": str(cut.id), "service": None}]}
        card = assistant.card(get("appointment.appointment.create"), booking, "es", person(hub_a, "es"))
        shown = list_field(card, "services")
    assert (shown["value"], shown.get(NAMED)) == ([{"service_id": "Corte de pelo"}], True)


def services_said(write: str, services: list, ctx: OperationContext) -> tuple:
    """What the card of ``write`` shows of the booking's ``services`` as sent: its value and whether it is ``named``."""
    shown = list_field(assistant.card(get(write), {"services": services}, ctx.language, ctx), "services")
    return shown["value"], shown.get(NAMED, False)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("write", sorted(BOOKS_SERVICES))
def test_the_card_names_a_service_the_assistant_sends_by_its_name(write, language, hub_a, no_fallback):
    """hub#860: with no id, the assistant sends the service as a person says it (``[{"service": "Tinte"}]``, as its
    schema invites) and the card said «Servicios: 1 elemento». Citas marks that text a name (``name_of``): the card says
    it, «Servicios: Tinte», alone or beside a service sent by its id."""
    with use_hub(hub_a):
        cut = make_service("Corte de pelo")
        ctx = person(hub_a, language)
        alone = services_said(write, [{"service": "Tinte"}], ctx)
        mixed = services_said(write, [{"service_id": str(cut.id)}, {"service": "Tinte"}], ctx)
    assert alone == ([{"service": "Tinte"}], True)
    assert mixed == ([{"service_id": "Corte de pelo"}, {"service": "Tinte"}], True)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(
    ("line", "said"),
    [
        ({"service_id": None, "service": "Tinte"}, {"service_id": None, "service": "Tinte"}),
        ({"service_id": "", "service": "Tinte"}, {"service_id": "", "service": "Tinte"}),
        ({"service_id": "CUT", "service": ""}, {"service_id": "Corte de pelo"}),
    ],
)
def test_an_empty_id_or_name_beside_the_other_still_names_the_service(line, said, hub_a, no_fallback):
    """rv-856: a model writes the datum it does not give as null or empty, in either place: the line still says its
    service, by the name sent or by its record (a null name beside its id: the test above)."""
    with use_hub(hub_a):
        cut = make_service("Corte de pelo")
        sent = {key: str(cut.id) if value == "CUT" else value for key, value in line.items()}
        shown = services_said("appointment.appointment.create", [sent], person(hub_a, "es"))
    assert shown == ([said], True)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_beside_its_id_the_card_says_the_service_booked_never_another_name(hub_a, no_fallback):
    """The booking takes the service by its id and ignores the name beside it (``resolve_services``): the card says the
    one it books, «Corte de pelo», not the «Tinte» the model wrote."""
    with use_hub(hub_a):
        cut = make_service("Corte de pelo")
        make_service("Tinte", duration=60)
        line = {"service_id": str(cut.id), "service": "Tinte"}
        shown = services_said("appointment.appointment.create", [line], person(hub_a, "es"))
    assert shown == ([{"service_id": "Corte de pelo"}], True)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_an_id_written_where_the_name_goes_is_never_said(hub_a, no_fallback):
    """rv-37: a model that mixes up the two data writes the id in the name's place: an id is no name, the card says how
    many services the booking carries."""
    with use_hub(hub_a):
        cut = make_service("Corte de pelo")
        shown = services_said("appointment.appointment.create", [{"service": str(cut.id)}], person(hub_a, "es"))
    assert shown[1] is False


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_name_beside_a_service_the_person_may_not_see_never_stands_for_it(hub_a, no_fallback):
    """Whoever may not read Services sees how many services the booking carries: never the name the model wrote beside
    an id the booking takes."""
    with use_hub(hub_a):
        cut = make_service("Corte de pelo")
        blind = person(hub_a, "es", without=frozenset({get("service.service.get").permission}))
        shown = services_said("appointment.appointment.create", [{"service_id": str(cut.id), "service": "Tinte"}], blind)
    assert shown == ([{}], True)


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


def appointment_writes() -> list:
    """Every write of Citas, a tool of the assistant or not: a reaction to another app may become one."""
    return [op for op in registry.values() if op.app_label == "appointment" and op.kind == "command"]


def test_no_datum_of_a_write_of_appointment_reaches_a_spanish_card_by_its_technical_name():
    """hub#637: in Spanish, the card said «Confirm Overlap», «Starts», «On Behalf Of Customer», «From Date», «To Date»
    and «Absorbed Id», the titles pydantic makes up from data no model of Citas names. Each write, with all its data:
    each datum by a name of its own, never that one (base's half is hub#258)."""
    writes = appointment_writes()
    assert len(writes) >= 25  # positive control: the registry has Citas's writes, the reactions among them
    assert technical_names(writes) == {}


#: The data of Citas's writes no model of it names (hub#637): each one is named by the title its schema gives it.
TITLED = [
    ("appointment.appointment.bulk_create", "confirm_overlap"),
    ("appointment.appointment.bulk_create", "starts"),
    ("appointment.appointment.cancel", "on_behalf_of_customer"),
    ("appointment.appointment.create", "confirm_overlap"),
    ("appointment.appointment.reschedule", "confirm_overlap"),
    ("appointment.appointment.reschedule", "on_behalf_of_customer"),
    ("appointment.appointment.update", "confirm_overlap"),
    ("appointment.customer.reassign", "absorbed_id"),
    ("appointment.recurring.materialize", "from_date"),
    ("appointment.recurring.materialize", "to_date"),
    ("appointment.recurring.update", "from_date"),
]


@pytest.mark.parametrize(("write", "datum"), TITLED)
def test_the_card_names_a_datum_no_model_names_by_its_title_in_the_persons_language(write, datum):
    """The title its schema gives the datum, in English as written and in Spanish as Citas's own catalogue says it:
    neither the one pydantic makes up nor another app's words for it."""
    op = get(write)
    title = op.input.model_fields[datum].title
    assert title and title != assistant._generated_title(datum)
    said = {
        language: [field["label"] for field in assistant.card(op, {datum: "x"}, language)["fields"]]
        for language in ("es", "en")
    }
    spanish = own_catalogue().gettext(title)
    assert spanish != title  # Citas's catalogue says it in Spanish
    assert said == {"es": [spanish], "en": [title]}
