"""What layer 1 of the assistant's QA says of Kitchen (erplora-next
docs/plans/2026-10-31-asistente-conocimiento-y-qa.md, the assistant's knowledge and QA): which tools it offers, to whom,
and the requests the real-model QA found unreachable (hub#1088).

Every ask of every tool of kitchen bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(kitchen is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks. Here, the people's own words:
a «comanda» is Sales' order to live (``order``, a table's check), so without Kitchen's asks its tickets, dishes and
routing were not among the tools a turn offers and the model answered with a check of Sales or with no tool at all. The
Hub says what the kitchen's words name (``base.assistant.SYNONYMS``): «la comanda» is also a kitchen ticket, an
«estación» or «el puesto» a station, «urgente» or «prisa» a rush, the «enrutado» the routing, a dish marked «como
listo» or «como hecho» is bumped and one sent back «a pendientes» or «a preparación» recalled.
"""

import json
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
#: What only who runs the kitchen holds (``KitchenConfig.role_permissions``): cancelling or deleting a ticket, the
#: stations and their routing, and the display's settings. An employee moves tickets and dishes, never these.
NOT_THE_EMPLOYEES = {
    "kitchen.ticket.cancel",
    "kitchen.ticket.delete",
    "kitchen.station.create",
    "kitchen.station.update",
    "kitchen.station.delete",
    "kitchen.routing.set",
    "kitchen.routing.clear",
    "kitchen.settings.update",
}

#: The requests of hub#1088's QA as the owner and the employee said them (``tests/e2e/qa/probes/*-es-kitchen-*.json``),
#: and nothing of the tools' ``asks``: before Kitchen said its asks, none of these tools was among the ones a turn
#: offers (``MAX_TOOLS``) but the list of tickets (13th) and the round sent apart (31st), so the model answered it had
#: no tool, sent the person to the display or chose a check of Sales.
REPORTED = [
    ("owner", "kitchen.routing.list", "¿a qué puesto se manda cada producto y cada familia del catálogo?"),
    ("owner", "kitchen.ticket.get", "¿cómo va la comanda «Comida personal QA», plato a plato?"),
    ("owner", "kitchen.ticket.list", "lista las comandas de hoy, incluidas las manuales y las que vienen del TPV"),
    ("owner", "kitchen.routing.set", "a partir de ahora manda el Café al puesto Plancha QA"),
    ("owner", "kitchen.item.bump", "marca como listos los dos cafés de «Comida personal QA» en Plancha QA"),
    (
        "owner",
        "kitchen.item.recall",
        "me equivoqué: devuelve a pendientes los cafés que acabo de marcar listos en «Comida personal QA»",
    ),
    ("owner", "kitchen.ticket.ready", "deja toda la comanda «Comida personal QA» terminada y esperando en el pase"),
    (
        "owner",
        "kitchen.ticket.recall",
        "retira del pase «Comida personal QA» y vuelve a ponerla en preparación porque falta un detalle",
    ),
    ("owner", "kitchen.ticket.set_rush", "pon «Comida personal QA» como urgente para que salte delante de las demás"),
    ("owner", "kitchen.ticket.reprint", "saca otra copia en Plancha QA de la comanda «Comida personal QA»"),
    (
        "owner",
        "kitchen.ticket.cancel",
        "anula la comanda «Comida personal QA» porque el empleado ha cambiado de idea, sin tocar ninguna cuenta del "
        "TPV",
    ),
    (
        "owner",
        "kitchen.ticket.delete",
        "borra la comanda manual «Comida personal QA», que ya no la necesito en el historial de trabajo",
    ),
    (
        "owner",
        "kitchen.ticket.send",
        "envía lo pendiente de la Cuenta QA aparte como una ronda urgente para llevar, con camarera Laura QA",
    ),
    (
        "owner",
        "kitchen.routing.clear",
        "quita la regla que enviaba el Café a Plancha QA; a partir de ahora seguirá su familia",
    ),
    (
        "employee",
        "kitchen.ticket.reprint",
        "vuelve a imprimir la comanda «Comida personal QA», que el papel se ha manchado",
    ),
]

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a probe of the QA may bring its tool: half of them, so
#: twenty tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
#: Every probe of layer 2 of Kitchen, the owner's and the employee's real phrases of the QA: the ones above and the ones
#: the model got right, and the employee's requests of what only who runs the kitchen may do (``refused``).
PROBES = [
    probe
    for path in sorted((Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes").glob("*-es-kitchen-*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
]
ROLES = {"owner": Membership.Role.OWNER, "employee": Membership.Role.EMPLOYEE}

#: The Hub's own words of the kitchen (``base.assistant.SYNONYMS``), in phrases nobody wrote as asks nor as probes, one
#: per group: each brings its tool among the first ten, and none does without its group. The dishes said «listos» need
#: live to read «listo» and «listos» as done, never as the action list (ERPlora/live#54), and their group too.
KITCHEN_WORDS = [
    ("¿cuántas comandas llevamos esta noche?", "kitchen.ticket.list"),
    ("lista los puestos con su impresora", "kitchen.station.list"),
    ("quita la urgencia a la mesa 3", "kitchen.ticket.set_rush"),
    ("¿qué enrutado tienen los productos de la carta?", "kitchen.routing.list"),
    ("da como listos los calamares de la 2", "kitchen.item.bump"),
    ("las bravas que di como listos vuelven a pendientes", "kitchen.item.recall"),
]


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def offered_place(tools: dict[str, Operation], name: str, phrase: str, language: str) -> int | None:
    """Where a turn that says ``phrase`` offers the tool ``name`` (1 the first), or ``None`` when it does not."""
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    return offered.index(name) + 1 if name in offered else None


def test_kitchen_offers_at_least_29_tools():
    """Kitchen's tools are at least 29 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "kitchen" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) >= 29


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_what_only_who_runs_the_kitchen_may_do(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert {"kitchen.item.bump", "kitchen.ticket.reprint"} <= set(employee)  # positive control: an employee cooks


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for *_, phrase in REPORTED] == [
        f"qa20261108.{role}.es.{name}" for role, name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("role", "name", "phrase"), REPORTED, ids=[f"{role}-{name}" for role, name, _ in REPORTED])
def test_the_reported_kitchen_request_is_offered_its_tool_without_being_its_asks(catalog_of, role, name, phrase):
    tools = catalog_of(ROLES[role], "es")
    assert name in tools  # positive control: the person holds the tool, so the model can receive it
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    place = offered_place(tools, name, phrase, "es")
    assert place is not None and place <= WITH_ROOM, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_kitchen_offers_its_tool_to_who_may_run_it(catalog_of, probe):
    """The owner's and the employee's phrases of layer 2, the ones the model answered right too: a tool of Kitchen that
    a new ask elsewhere pushes far down the ones a turn offers fails here before the real-model QA sees it; what the
    employee may not do is not in their catalogue at all, so the model can only say so."""
    assert (probe["app"], probe["language"]) == ("kitchen", "es")
    tools = catalog_of(ROLES[probe["role"]], probe["language"])
    name, phrase = probe["tool"], probe["phrase"]
    if probe["expect"] == "refused":
        assert name not in tools
        assert name in catalog_of(Membership.Role.OWNER, probe["language"])  # positive control: it is a real tool
        return
    assert name in tools  # positive control: the person holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    place = offered_place(tools, name, phrase, probe["language"])
    assert place is not None and place <= WITH_ROOM, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("phrase", "name"), KITCHEN_WORDS, ids=[name for _, name in KITCHEN_WORDS])
def test_the_kitchens_own_words_bring_the_tool_they_mean_among_the_first_ten(catalog_of, phrase, name):
    tools = catalog_of(ROLES["owner"], "es")
    assert name in tools  # positive control: the owner holds it, so only the selection can leave it out
    assert comparable(phrase) not in probe_phrases()  # nobody's probe: the phrase measures the words, not a copy
    assert all(
        comparable(phrase) != comparable(ask) for op in tools.values() for ask in shared.asks_of(op).get("es", ())
    )
    place = offered_place(tools, name, phrase, "es")
    assert place is not None and place <= 10, place
