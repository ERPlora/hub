"""What layer 1 of the assistant's QA says of Kitchen: which tools it offers, to whom, and the requests the real-model
QA found unreachable (hub#1088).

Every ask of every tool of kitchen bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(kitchen is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks. Here, the people's own words:
a «comanda» is Sales' order to live (``order``, a table's check), so without Kitchen's asks its tickets, dishes and
routing were not among the tools a turn offers and the model answered with a check of Sales or with no tool at all. The
Hub says what the kitchen's words name (``base.assistant.SYNONYMS``): «la comanda» is also a kitchen ticket, an
«estación» or «el puesto» a station, «urgente» or «prisa» a rush, the «enrutado» and the «regla» that sends a dish to
a station the routing, a dish marked «como listo» or «como hecho» is bumped and one sent back «a pendientes» or «a
preparación» recalled.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import TOP, assert_offered_with_room, comparable, offered_place, probe_phrases
from base.tests.test_assistant_asks import english_coverage_test, english_words_test, nobodys_words, own_words_test
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

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
#: live to read «listo» and «listos» as done, never as the action list, and their group too.
KITCHEN_WORDS = [
    ("¿cuántas comandas llevamos esta noche?", "kitchen.ticket.list"),
    ("lista los puestos con su impresora", "kitchen.station.list"),
    ("quita la urgencia a la mesa 3", "kitchen.ticket.set_rush"),
    ("¿qué enrutado tienen los productos de la carta?", "kitchen.routing.list"),
    ("pon una regla para que las bebidas salgan por la Barra", "kitchen.routing.set"),
    ("da como listos los calamares de la 2", "kitchen.item.bump"),
    ("las bravas que di como listos vuelven a pendientes", "kitchen.item.recall"),
]
#: What a person says in words of their own, neither an ask nor a probe of layer 2 (nor an ask with a word changed),
#: for the nineteen tools whose probes a turn offers without their asks too (by their name, their description or the
#: Hub's words above): here it is their asks that bring the tool among the first ten, so asks that stop reading as
#: people speak fail. Language, tool, phrase.
OWN_WORDS = [
    ("es", "kitchen.ticket.list", "dime las que se anularon esta mañana"),
    ("es", "kitchen.ticket.notices", "¿qué ha llegado hace un momento?"),
    ("en", "kitchen.ticket.get", "which dishes of number 9 are still to go?"),
    ("es", "kitchen.ticket.by_order", "¿la cuenta de la 6 ha mandado alguna ronda?"),
    ("en", "kitchen.station.list", "which ones have we got and what goes to each of them?"),
    ("es", "kitchen.settings.get", "¿a qué minuto pasa a ámbar?"),
    ("es", "kitchen.log.list", "¿qué se hizo ayer con los platos de la plancha?"),
    ("es", "kitchen.ticket.receive", "que salga en pantalla la ronda que han mandado de la 6"),
    ("es", "kitchen.ticket.create", "rehaz a mano la ensalada de la 5"),
    ("en", "kitchen.ticket.start", "get number 9 cooking now"),
    ("es", "kitchen.ticket.cancel", "que no se haga la 9, se han ido"),
    ("es", "kitchen.ticket.delete", "esa que hice a mano ya está anulada: bórrala"),
    ("es", "kitchen.ticket.set_rush", "que la 9 salga la primera"),
    ("es", "kitchen.item.bump", "las croquetas de la 3 ya están hechas"),
    ("es", "kitchen.station.create", "quiero una estación para los postres"),
    ("es", "kitchen.station.update", "que la Barra solo salga en pantalla"),
    ("es", "kitchen.station.delete", "ya no usamos la de postres, quítala"),
    ("es", "kitchen.routing.set", "las bebidas, que salgan por la Barra"),
    ("es", "kitchen.settings.update", "la pantalla suena demasiado, bájale el sonido"),
]
#: The places an ask of another app keeps free below the first ten: the asks of the next app to say its own take them.
ROOM = 2


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
    assert_offered_with_room(catalog_of(ROLES[role], "es"), name, phrase, "es")


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
    assert_offered_with_room(tools, name, phrase, probe["language"])


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("phrase", "name"), KITCHEN_WORDS, ids=[name for _, name in KITCHEN_WORDS])
def test_the_kitchens_own_words_bring_the_tool_they_mean_among_the_first_ten(catalog_of, phrase, name):
    tools = catalog_of(ROLES["owner"], "es")
    assert nobodys_words(tools, phrase, "es")
    assert_offered_with_room(tools, name, phrase, "es", room=TOP)


test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks = own_words_test(
    OWN_WORDS, ids=[name for _, name, _ in OWN_WORDS]
)


#: What the owner says in English in words of their own for each tool of Kitchen that needs one, neither
#: an ask nor a probe of layer 2: its English asks lift it among the first ten (``assert_its_asks_lift``).
OWN_WORDS_EN = [
    ("kitchen.item.bump", "the croquettes for number 3 are done"),
    ("kitchen.item.recall", "number 4's steak isn't done after all"),
    ("kitchen.log.list", "who voided number 15 yesterday?"),
    ("kitchen.routing.clear", "stop sending desserts anywhere"),
    ("kitchen.routing.list", "where do drinks and desserts go?"),
    ("kitchen.routing.set", "drinks should come out at the Bar"),
    ("kitchen.settings.get", "at what minute does it turn amber?"),
    ("kitchen.settings.update", "make it go red sooner"),
    ("kitchen.station.create", "we need a pastry one that prints on paper"),
    ("kitchen.station.delete", "the old pastry one can go"),
    ("kitchen.station.update", "the desserts one should be screen only"),
    ("kitchen.ticket.all_day", "how many burgers do we still have to make?"),
    ("kitchen.ticket.board", "what's left to cook right now?"),
    ("kitchen.ticket.by_order", "has table 6's check sent any rounds?"),
    ("kitchen.ticket.cancel", "don't make number 9, they've left"),
    ("kitchen.ticket.create", "remake number 5's salad by hand"),
    ("kitchen.ticket.delete", "the crew meal I made by hand: get rid of it"),
    ("kitchen.ticket.list", "tell me the ones that got cancelled this morning"),
    ("kitchen.ticket.notices", "anything just come in a moment ago?"),
    ("kitchen.ticket.ready", "everything on number 9 can go to the pass"),
    ("kitchen.ticket.recall", "number 3 isn't finished, bring it back from the pass"),
    ("kitchen.ticket.receive", "take in the round table 6 just sent"),
    ("kitchen.ticket.reprint", "the paper jammed, print number 9 again"),
    ("kitchen.ticket.send", "fire what's left on table 6"),
    ("kitchen.ticket.serve", "number 9 has left the pass, it's gone out"),
    ("kitchen.ticket.set_rush", "number 9 has to go first, they're in a hurry"),
]
test_a_request_in_english_is_lifted_by_its_english_asks = english_words_test(OWN_WORDS_EN)
ENGLISH_ABOVE = [name for language, name, _ in OWN_WORDS if language == "en"]
test_each_tool_has_its_own_english_words = english_coverage_test("kitchen", OWN_WORDS_EN, ENGLISH_ABOVE)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", list(Membership.Role))
def test_kitchen_takes_no_place_from_who_has_been_serving_tables(catalog_of, role):
    """«Serving» names ``kitchen.ticket.serve``, whose asks say «servida»: Tables' «who has been serving tables?» came
    11th with them, past the tenth place ``base/tests/test_assistant_asks.py`` allows (it was tenth already). Its asks
    in English keep two places free."""
    tools = catalog_of(role, "en")
    assert {"table.waiter.list", "kitchen.ticket.serve"} <= set(tools)  # positive control: both compete in the ranking
    asks = shared.asks_of(tools["table.waiter.list"])["en"]
    places = {ask: offered_place(tools, "table.waiter.list", ask, "en") for ask in asks}
    assert {ask: place for ask, place in places.items() if place is None or place > TOP - ROOM} == {}
