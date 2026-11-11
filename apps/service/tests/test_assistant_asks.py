"""What layer 1 of the assistant's QA does not say of Services (docs plan 2026-10-31, the assistant's knowledge and QA,
§3): how many tools it offers, that the owner's requests of the real-model QA (hub#1104), in the owner's own words, are
offered their existing operation, that a record a tool takes by its id says which read finds it, and that what
Services' tools say to be asked for takes no place from the operations of Sales and Appointments a request is for.

Every ask of every tool of service bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (service is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over the
asks and the guard that no ask copies a probe of layer 2.
"""

import dataclasses
import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tests.test_assistant_asks import comparable, probe_phrases

A = Scope("host", "a")
PROBES_DIR = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"

#: The requests of hub#1104's QA (``tests/e2e/qa/probes/owner-es-service-2026-11-08.json``) as the owner said them, and
#: nothing of the tools' ``asks``: before Services said its asks, six of these tools were not among the ones a turn
#: offers (``MAX_TOOLS``) and the rest came 7th to 16th, so the model answered it had no tool, asked for ids or chose a
#: tool of another app (Online booking's settings to restore a service, a role to take a professional off a service).
REPORTED = [
    ("service.grant.get", "abre el Bono QA vendido a Ana QA con fecha, saldo y sesiones usadas"),
    ("service.package.list", "¿qué bonos vendo, con precio cerrado, sesiones incluidas y días de validez?"),
    ("service.session.get", "abre la sesión de Bono QA que está retenida para una línea del TPV y dime su estado"),
    ("service.assignment.assign", "asigna Corte QA a Camarera Ventas QA, con 30 minutos y 12 € como condiciones propias"),
    (
        "service.grant.redeem",
        "gasta una sesión del Bono extra QA de Ana QA en un Corte QA fuera del TPV, vinculada a su próxima cita",
    ),
    ("service.assignment.remove", "quita a Camarera Ventas QA de Corte QA para que deje de hacerlo"),
    (
        "service.assignment.update",
        "cambia la asignación de Camarera Ventas QA a Corte QA: 45 minutos y 14 €, como servicio principal",
    ),
    ("service.grant.void", "anula el Bono QA nuevo de Ana QA porque se vendió por error, sin tocar dinero"),
    ("service.service.restore", "restaura Masaje QA para volver a venderlo y reservarlo"),
    (
        "service.session.hold",
        "reserva una sesión del Bono QA de Ana QA para la línea Corte QA de Cuenta bonos QA durante hoy",
    ),
    (
        "service.session.release",
        "libera la sesión retenida del Corte QA de Cuenta bono retirada QA para devolverla al bono",
    ),
]

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a request of the QA may bring its tool: half of them, so
#: twenty tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
#: Every probe of layer 2 of Services, the owner's real phrases of the QA: the eleven above and the ones the model got
#: right.
PROBES = json.loads((PROBES_DIR / "owner-es-service-2026-11-08.json").read_text(encoding="utf-8"))["probes"]

#: The tools that take a record by its id alone, and the read that finds that id by what a person names it with (the
#: customer who owns a voucher, the service and the professional of an assignment, the line of a check a session pays):
#: its description says that read, so the model looks the record up instead of asking the person for an id they never
#: see (hub#1104: «pide el id del bono», «pide el id de la sesión»).
FOUND_BY = {
    "service.grant.get": "service.grant.list",
    "service.grant.void": "service.grant.list",
    "service.grant.void_check": "service.grant.list",
    "service.grant.adjust": "service.grant.list",
    "service.grant.adjust_check": "service.grant.list",
    "service.grant.redeem": "service.grant.list",
    "service.grant.redeem_check": "service.grant.list",
    "service.session.get": "sale.order.get",
    "service.session.release": "sale.order.get",
    "service.assignment.get": "service.assignment.list",
    "service.assignment.remove": "service.assignment.list",
    "service.assignment.update": "service.assignment.list",
}


def neighbour_probes() -> list[dict]:
    """The probes of layer 2 of the owner, in Spanish, of Appointments and of Sales' checks: the requests whose words
    («el bono», «la sesión», «la profesional», «el servicio») are Services' too."""
    return [
        probe
        for path in sorted(PROBES_DIR.glob("owner-es-*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
        if probe["tool"].startswith(("appointment.", "sale.order."))
    ]


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def place(tools: dict[str, Operation], name: str, phrase: str, language: str = "es") -> int | None:
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    return offered.index(name) + 1 if name in offered else None


def without_services_asks(tools: dict[str, Operation]) -> dict[str, Operation]:
    """``tools`` with Services' tools saying no asks: how a turn ranked them before Services said its own."""
    return {
        name: dataclasses.replace(op, ai={key: value for key, value in op.ai.items() if key != "asks"})
        if op.app_label == "service"
        else op
        for name, op in tools.items()
    }


def test_services_offers_at_least_46_tools():
    """Services' tools are at least 46 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "service" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) >= 46


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [f"owner.es.{name}" for name, _ in REPORTED]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_service_request_offers_its_existing_operation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    found = place(tools, name, phrase)
    assert found is not None and found <= WITH_ROOM, found


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_services_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's forty-six phrases of layer 2, the ones the model answered right too: a tool of Services that a new
    ask elsewhere pushes out of the ones a turn offers fails here before the real-model QA sees it."""
    assert (probe["app"], probe["role"], probe["language"]) == ("service", "owner", "es")
    tools = catalog_of(Membership.Role.OWNER, probe["language"])
    name, phrase = probe["tool"], probe["phrase"]
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    found = place(tools, name, phrase)
    assert found is not None and found <= WITH_ROOM, found


@pytest.mark.parametrize(("name", "read"), sorted(FOUND_BY.items()))
def test_a_record_taken_by_its_id_says_which_read_finds_it(name, read):
    op = registry[name]
    assert list(op.input.model_fields)[0] in {"id", "ids"}  # positive control: it takes the record by its id
    assert assistant.is_tool(registry[read]) and registry[read].kind == "query"
    assert read in op.ai["description"], name


def test_the_hub_reads_a_bono_as_a_voucher_of_services_and_an_asignacion_as_an_assignment():
    """``base.assistant.SYNONYMS``: «el bono» names Services' voucher, the one of the catalogue and the one sold
    (``service.package``, ``service.grant``), and «la asignación», or what one «asigna», a professional's assignment
    to a service (``service.assignment``); without the Hub's groups, none of them does (positive control)."""
    for phrase, wanted in (
        ("anula el bono de Marta", "grant"),
        ("¿qué bonos ofrecemos?", "package"),
        ("asigna los peinados a Lucas", "assignment"),
        ("cambia la asignación de Lucas", "assignment"),
    ):
        concepts = shared.asked([phrase], assistant.SYNONYMS).concepts
        assert any(shared.stem(wanted) in concept for concept in concepts), phrase
        assert not any(shared.stem(wanted) in concept for concept in shared.asked([phrase]).concepts), phrase


#: Requests in the owner's words that are neither an ask nor a probe of layer 2: each brings its tool among the first
#: ten only because the Hub reads «bono» as Services' voucher and «asigna» as an assignment.
BY_THE_GROUPS = [
    ("service.assignment.assign", "asigna los cortes de caballero a Marta, con 25 minutos"),
    ("service.assignment.update", "cambia la asignación de Lucas a los peinados: ahora tarda media hora"),
    ("service.package.list", "¿qué bonos hay para comprar?"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), BY_THE_GROUPS)
def test_the_groups_of_services_bring_a_new_request_to_its_tool(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert comparable(phrase) not in probe_phrases()
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    assert name in ranked(tools, phrase)[:10]
    assert name not in ranked(tools, phrase, without_services_groups())[:10]


#: Services' own records that the words of a check or an appointment («el bono», «la sesión», «asigna») are of too:
#: its vouchers (of the catalogue, sold, and their movements), their sessions and its professionals' assignments.
VOUCHERS_SESSIONS_ASSIGNMENTS = (
    "service.package.",
    "service.grant.",
    "service.movement.",
    "service.session.",
    "service.assignment.",
)
#: A request that names an assignment itself («las citas que no tengan nadie asignado», as «asigna» does): Services'
#: assignments are what it names, so they may come ahead of its tool by the Hub's group (measured on this branch: the
#: diary's lanes, 8th → 9th, behind ``service.assignment.list``); by Services' asks, never.
NAMES_AN_ASSIGNMENT = re.compile(r"\basign", re.IGNORECASE)


def without_services_groups() -> tuple[tuple[str, ...], ...]:
    """``base.assistant.SYNONYMS`` without the groups Services adds: «bono» and «asignación»."""
    kept = tuple(group for group in assistant.SYNONYMS if not {"bono", "asignacion"} & set(group))
    assert len(assistant.SYNONYMS) - len(kept) == 2  # positive control: both of Services' groups are there
    return kept


def ranked(tools: dict[str, Operation], phrase: str, synonyms: tuple | None = None) -> list[str]:
    """The tools a turn offers for ``phrase`` in Spanish, as ``base.assistant.RANKING`` ranks, with ``synonyms``."""
    ranking = {**assistant.RANKING} if synonyms is None else {**assistant.RANKING, "synonyms": synonyms}
    return [op.name for op in shared.relevant(tools, [phrase], "es", **ranking)]


def passed_by(offered: list[str], name: str) -> set[str] | None:
    """Services' vouchers, sessions and assignments ahead of ``name`` in ``offered``; ``None`` when it is not offered."""
    if name not in offered:
        return None
    return {other for other in offered[: offered.index(name)] if other.startswith(VOUCHERS_SESSIONS_ASSIGNMENTS)}


def lost_places(before: list[str], now: list[str], name: str) -> set[str] | None:
    """What of Services passes ``name`` now that did not before; ``None`` when it is no longer offered at all."""
    then, after = passed_by(before, name), passed_by(now, name)
    if then is None:
        return set()
    return None if after is None else after - then


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_services_asks_take_no_place_from_sales_nor_appointments(catalog_of):
    """Each request of Appointments and of Sales' checks of layer 2 that a turn offers its tool for keeps it ahead of the
    same vouchers, sessions and assignments of Services whether their tools say their asks or not: none climbs past it
    by its asks (paying a line with a voucher is ``sale.order.apply_voucher``'s, not a session's)."""
    probes = neighbour_probes()
    assert len(probes) > 40  # positive control: the probes of Appointments and of Sales' checks are read
    tools = catalog_of(Membership.Role.OWNER, "es")
    before = without_services_asks(tools)
    assert not any(shared.asks_of(op) for op in before.values() if op.app_label == "service")
    assert any(shared.asks_of(op) for op in tools.values() if op.app_label == "service")
    lost = {}
    for probe in probes:
        name, phrase = probe["tool"], probe["phrase"]
        if (passed := lost_places(ranked(before, phrase), ranked(tools, phrase), name)) != set():
            lost[probe["id"]] = passed
    assert lost == {}


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_services_groups_take_no_place_from_sales_nor_appointments(catalog_of):
    """The same requests, with and without the Hub's groups of Services («bono», «asignación»): none loses its place to
    a voucher, a session or an assignment of Services, unless the request names an assignment itself."""
    probes = neighbour_probes()
    tools = catalog_of(Membership.Role.OWNER, "es")
    without = without_services_groups()
    lost, named = {}, []
    for probe in probes:
        name, phrase = probe["tool"], probe["phrase"]
        if (passed := lost_places(ranked(tools, phrase, without), ranked(tools, phrase), name)) != set():
            if NAMES_AN_ASSIGNMENT.search(phrase) and passed:
                named.append(probe["id"])
                continue
            lost[probe["id"]] = passed
    assert lost == {}
    assert set(named) <= {"owner.es.appointment.agenda.lanes"}  # the one measured: a new one is a choice to look at
