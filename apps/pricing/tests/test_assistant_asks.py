"""What layer 1 of the assistant's QA says of Price lists: which tools it offers, what an employee is never offered,
and that the owner's requests of the real-model QA (hub#1101), in the owner's own words, are offered their existing
operation.

Every ask of every tool of pricing bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(pricing is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks and the guard that no ask copies
a probe of layer 2.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import assert_offered_with_room, comparable, english_coverage_test, english_words_test
from base.tests.test_assistant_asks import offered_to, own_words_test, probe_phrases
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

#: Every write of Price lists is ``pricing.manage``, which an employee lacks (they only read the prices,
#: ``pricing.view``): an employee's assistant is never offered one.
NOT_THE_EMPLOYEES = {
    "pricing.price_list.create",
    "pricing.price_list.update",
    "pricing.price_list.set_default",
    "pricing.price_list.deactivate",
    "pricing.price_list.activate",
    "pricing.price_item.add",
    "pricing.price_item.update",
    "pricing.price_item.remove",
    "pricing.rule.create",
    "pricing.rule.update",
    "pricing.rule.deactivate",
    "pricing.rule.activate",
}
#: Its reads: the price lists, their prices, the discount rules, what they point at in another app and a line's price.
READS = {
    "pricing.price_list.list",
    "pricing.price_list.get",
    "pricing.price_item.list",
    "pricing.price_item.get",
    "pricing.rule.list",
    "pricing.rule.get",
    "pricing.catalog.get",
    "pricing.price.resolve",
}

#: The requests of hub#1101's QA (``tests/e2e/qa/probes/owner-es-pricing-2026-11-08.json``) as the owner said them,
#: and nothing of the tools' ``asks``: before Price lists said its asks, bringing a list or a rule back was among none
#: of the tools a turn offers (``MAX_TOOLS``) and adding a price or switching a rule off came last but one, so the model
#: answered it could not change prices, looked for an app or a product, or took the rule for a voucher or a payment
#: method.
REPORTED = [
    ("pricing.price_item.add", "pone en Mayorista QA el Café a 1,50 € desde una unidad"),
    ("pricing.price_list.activate", "vuelve a activar Mayorista QA para las próximas ventas"),
    ("pricing.rule.deactivate", "desactiva Descuento QA sin perder su configuración"),
    ("pricing.rule.activate", "vuelve a activar Descuento QA para las nuevas ventas"),
]
#: What the model ran instead of bringing a rule back, a payment method to switch on, and what it looked for instead of
#: bringing a price list back, an app. live reads «activar» as the action ``activate`` too, not only as turning
#: something on, so bringing a price list or a rule back goes ahead of ``base.app.enable``.
CHOSEN_INSTEAD = [
    ("pricing.rule.activate", "payment.method.activate"),
    ("pricing.price_list.activate", "base.app.enable"),
    ("pricing.rule.activate", "base.app.enable"),
]

#: Every probe of layer 2 of Price lists, the owner's real phrases of the QA: the four above and the ones the model got
#: right (or answered with an equivalent list).
PROBES = json.loads(
    (Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes" / "owner-es-pricing-2026-11-08.json").read_text(
        encoding="utf-8"
    )
)["probes"]

#: What a person says in words of their own, neither an ask nor a probe of layer 2, one for each tool: it is their asks
#: that bring the tool among the first ten (a «tarifa» or a «precio» named brings every tool of Price lists by its
#: name, so none says it; nor «importe», which reads as Import's, «artículo», Inventory's product, «sale», a sale, or
#: «ahora», which the apps of people and of the till read too), and asks that stop reading as people speak fail. None is
#: an ask of its tool with its words moved around: what it shares with them comes from more than one ask.
OWN_WORDS = [
    ("pricing.price_list.list", "¿qué trato especial les doy a los distribuidores?"),
    ("pricing.price_list.get", "¿hasta qué día vale lo de Hostelería?"),
    ("pricing.price_list.create", "quiero dar de alta otra más para el club, que se llame Club Oro"),
    ("pricing.price_list.update", "la de verano tiene que acabar más tarde, a finales de octubre"),
    ("pricing.price_list.set_default", "Distribuidores pasa a ser la de todo el que no tenga otra"),
    ("pricing.price_list.deactivate", "congela lo de verano hasta el año que viene"),
    ("pricing.price_list.activate", "que vuelva a contar lo de invierno para los distribuidores"),
    ("pricing.price_item.list", "¿cómo tengo puesto el croissant en Hostelería y en las demás?"),
    ("pricing.price_item.get", "¿desde cuántas unidades vale lo del croissant en Socios?"),
    ("pricing.price_item.add", "agrega la caña a los socios a 1,10"),
    ("pricing.price_item.update", "la magdalena en Hostelería se queda en 1,60"),
    ("pricing.price_item.remove", "que el zumo de Distribuidores vuelva a costar lo de siempre"),
    ("pricing.rule.list", "¿qué rebajas van solas en la tienda?"),
    ("pricing.rule.get", "¿qué hace exactamente la promo de verano y hasta cuándo dura?"),
    ("pricing.rule.create", "monta una oferta de 3x2 para los socios"),
    ("pricing.rule.update", "modifica lo de verano para que quite un cuarto"),
    ("pricing.rule.deactivate", "aparca el dos por uno de los zumos hasta que vuelva el calor"),
    ("pricing.rule.activate", "recupera el 2x1 de zumos de otros veranos"),
    ("pricing.catalog.get", "¿a qué grupo corresponde ese identificador de lo de Socios?"),
    ("pricing.price.resolve", "Nuria quiere dos cañas, ¿cuánto le cuestan a ella?"),
]


def test_price_lists_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """Price lists is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its asks
    for every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "pricing" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_pricing_offers_its_twenty_tools():
    """Price lists' tools are its reads and its writes (``AI``, never ``INTERNAL``; its reactions to other apps are no
    tool): a silent drop of a tool fails."""
    tools = {name for name, op in registry.items() if op.app_label == "pricing" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert tools == READS | NOT_THE_EMPLOYEES
    assert {name for name, _ in OWN_WORDS} == tools  # one phrase of a person's own words for each tool


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_what_only_who_manages_the_prices_may_do(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES | READS <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee), sorted(NOT_THE_EMPLOYEES & set(employee))
    assert READS <= set(employee)  # positive control: an employee reads the prices and asks what a line costs


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"owner.es.{name}" for name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_pricing_request_offers_its_existing_operation(catalog_of, name, phrase):
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, "es"), name, phrase)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "instead"), CHOSEN_INSTEAD)
def test_the_reported_request_to_bring_back_offers_its_tool_before_the_one_the_model_ran(catalog_of, name, instead):
    tools = catalog_of(Membership.Role.OWNER, "es")
    phrase = dict(REPORTED)[name]
    names = offered_to(tools, phrase)
    assert instead in tools  # positive control: what the model ran is a tool of the owner too
    assert name in names, names[:10]
    assert instead not in names or names.index(name) < names.index(instead), names[:10]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_price_lists_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's twenty phrases of layer 2, the ones the model answered right too: a tool of Price lists that a new
    ask elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees it."""
    assert (probe["app"], probe["role"], probe["language"]) == ("pricing", "owner", "es")
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, probe["language"]), probe["tool"], probe["phrase"])


test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks = own_words_test(OWN_WORDS, "es")


#: What the owner says in English in words of their own for each tool of Price lists that needs one, neither
#: an ask nor a probe of layer 2: its English asks lift it among the first ten (``assert_its_asks_lift``).
OWN_WORDS_EN = [
    ("pricing.catalog.get", "what group is behind that code of the partners?"),
    ("pricing.price.resolve", "Nuria wants two beers, work out what she pays"),
    ("pricing.price_item.add", "put the orange juice in Hospitality at 1.50"),
    ("pricing.price_item.get", "how much is a beer for the partners, from how many?"),
    ("pricing.price_item.list", "what does the croissant cost in each of them?"),
    ("pricing.price_item.remove", "Distributors should pay for the juice like everybody else"),
    ("pricing.price_item.update", "the muffin in Hospitality is 1.60 now"),
    ("pricing.price_list.activate", "the winter one should apply again for distributors"),
    ("pricing.price_list.create", "a separate one for the club, call it Club Oro"),
    ("pricing.price_list.deactivate", "switch off the summer one until next year, keep what it has"),
    ("pricing.price_list.get", "does Hospitality end at some point this year?"),
    ("pricing.price_list.list", "what special treatment do I give the distributors?"),
    ("pricing.price_list.set_default", "make the partners' one apply to everybody else"),
    ("pricing.price_list.update", "the summer one should last longer, until late October"),
    ("pricing.rule.activate", "bring back the 2x1 on juices from other summers"),
    ("pricing.rule.create", "a reduction on toasts for partners who take three"),
    ("pricing.rule.deactivate", "put the juice deal aside, but keep it for next summer"),
    ("pricing.rule.get", "what exactly does the summer promo do and how long does it last?"),
    ("pricing.rule.list", "what's running now in the shop that applies by itself?"),
    ("pricing.rule.update", "raise what the summer one takes off to a quarter"),
]
test_a_request_in_english_is_lifted_by_its_english_asks = english_words_test(OWN_WORDS_EN)
test_each_tool_has_its_own_english_words = english_coverage_test("pricing", OWN_WORDS_EN)
