"""What layer 1 of the assistant's QA does not say of Taxes (docs plan 2026-10-31, the assistant's knowledge and QA,
§3): how many tools it offers, what an employee is never offered, and that the requests of the real-model QA
(hub#1094), in the person's own words, are offered their existing operation.

Every ask of every tool of tax bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (tax is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over the
asks and the guard that no ask copies a probe of layer 2.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import (
    assert_its_asks_bring,
    catalog_of,  # noqa: F401 (a fixture: the tests below take it by name)
    comparable,
    place_of_no_ask,
    probe_phrases,
)

#: Taxes' assistant tools: its reads (the calculator, categories, rules, aliases and the business's tax region) and
#: its writes (categories, aliases, rules one by one or in a batch, their end, deactivation and reactivation, and the
#: region). ``tax.rule.get`` is ``INTERNAL``: it only names a rule on a confirmation card.
TOOLS = {
    "tax.rate.calculate",
    "tax.category.list",
    "tax.category.get",
    "tax.rule.list",
    "tax.rule.status",
    "tax.rule.parent_candidates",
    "tax.rule.countries",
    "tax.alias.list",
    "tax.alias.resolve",
    "tax.settings.get",
    "tax.category.create",
    "tax.alias.create",
    "tax.rule.create",
    "tax.rule.bulk_create",
    "tax.rule.end",
    "tax.rule.deactivate",
    "tax.rule.activate",
    "tax.settings.update",
}
#: What decides what is charged and declared (``tax.manage``): who runs the business and a manager hold it, an
#: employee only reads and calculates (``TaxConfig.role_permissions``).
THE_WRITES = {name for name in TOOLS if registry[name].kind == "command"}

#: The requests of hub#1094's QA (``tests/e2e/qa/probes/owner-es-tax-2026-11-08.json``) as the owner said them, and
#: nothing of the tools' ``asks``: before Taxes said its asks, none of these tools was among the ones a turn offers
#: (``MAX_TOOLS``), so the model sent the owner to the screen, looked for an automation or said it could not change a
#: rule.
REPORTED = [
    ("tax.rule.deactivate", "desactiva temporalmente la regla española de product.qa sin perder su porcentaje ni sus fechas"),
    ("tax.rule.activate", "vuelve a activar la regla española de product.qa que acabo de desactivar"),
    ("tax.rule.end", "haz que la regla española de product.qa deje de aplicarse después del 31/12/2026 inclusive"),
]

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a request of the QA may bring its tool: half of them, so
#: twenty tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
#: Every probe of layer 2 of Taxes, the owner's and the employee's real phrases of the QA: the three above and the
#: ones the model got right.
PROBES = [
    probe
    for path in sorted((Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes").glob("*-es-tax-*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
]
ROLES = {"owner": Membership.Role.OWNER, "employee": Membership.Role.EMPLOYEE}
#: live reads «activar» and «desactivar» as the actions ``activate`` and ``deactivate`` (ERPlora/live#70), but it takes
#: an app named in a «de» complement of the thing («la regla española de product.qa»: Products) for what the command
#: switches: bringing a rule back or switching it off is offered, but after the app's switch the model reached for
#: instead. Strict, so the pointer of live that reads the head of the object turns these red and whoever brings it takes
#: the mark off: the order is then held.
UNTIL_LIVE_READS_WHAT_IS_SWITCHED = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="ERPlora/live#73: «de product.qa» names the Products app, taken for what the command switches",
)
#: What a turn offers ahead of the reported requests to bring a rule back or to switch it off: an app's switch.
CHOSEN_INSTEAD = [
    pytest.param("tax.rule.activate", "base.app.enable", marks=UNTIL_LIVE_READS_WHAT_IS_SWITCHED),
    pytest.param("tax.rule.deactivate", "base.app.disable", marks=UNTIL_LIVE_READS_WHAT_IS_SWITCHED),
]
#: What a person says in words of their own, neither an ask nor a probe of layer 2, one for each tool: it is their asks
#: that bring the tool among the first ten, and without them it is not there (hub#1135, hub#1165), so asks that stop
#: reading as people speak fail. None shares more than two stems with any one ask of its tool.
OWN_WORDS = [
    ("tax.rate.calculate", "de 60 € en libros, ¿qué parte se va en IVA?"),
    ("tax.category.list", "¿qué tipos de IVA puedo dar a un producto?"),
    ("tax.category.get", "¿existe ya algo para el calzado entre las categorías de impuestos?"),
    ("tax.rule.list", "¿a cuánto tengo el tipo del calzado y desde cuándo?"),
    ("tax.rule.status", "¿el negocio tiene ya impuestos en vigor para arrancar?"),
    ("tax.rule.parent_candidates", "¿qué reglas sirven de padre para el recargo del calzado?"),
    ("tax.rule.countries", "¿para qué países están puestos los impuestos?"),
    ("tax.alias.list", "¿qué alias guardé para leer los ficheros de productos?"),
    ("tax.alias.resolve", "el texto «IGIC 7», ¿a qué categoría corresponde?"),
    ("tax.settings.get", "¿llevamos IGIC en la tienda?"),
    ("tax.category.create", "haz una categoría para el calzado con su IVA"),
    ("tax.alias.create", "guarda el alias «menú diario» para la comida"),
    ("tax.rule.create", "el pan va al 4 %: dale su regla de IVA"),
    ("tax.rule.bulk_create", "mete de golpe los tipos de IVA de Francia de 2026"),
    ("tax.rule.end", "el tipo del calzado se acaba en julio: dale a su regla su último día"),
    ("tax.rule.deactivate", "deja en suspenso el IVA del calzado"),
    ("tax.rule.activate", "recupera el IVA del calzado"),
    ("tax.settings.update", "nos mudamos a Ceuta: que los impuestos sean los de allí"),
]


def assert_offered_with_room(tools: dict[str, Operation], name: str, phrase: str) -> None:
    """That ``phrase``, a person's real words of layer 2 and none of the asks of tool ``name``, brings it among the first
    ``WITH_ROOM`` a turn offers."""
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= WITH_ROOM, place


def test_tax_offers_its_eighteen_tools():
    """Taxes' assistant tools (``AI``, never ``INTERNAL``): a silent drop of a tool fails."""
    tools = {name for name, op in registry.items() if op.app_label == "tax" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert tools == TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_what_decides_what_is_charged(catalog_of):
    for role in (Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER):
        assert {name for name in catalog_of(role, "es") if name.startswith("tax.")} == TOOLS, role
    employee = {name for name in catalog_of(Membership.Role.EMPLOYEE, "es") if name.startswith("tax.")}
    assert employee == TOOLS - THE_WRITES
    assert "tax.rate.calculate" in employee  # positive control: an employee reads and calculates


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"qa20261108.owner.es.{name}" for name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_tax_request_offers_its_existing_operation(catalog_of, name, phrase):
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, "es"), name, phrase)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_taxes_offers_its_tool_to_whoever_may_run_it(catalog_of, probe):
    """The owner's and the employee's phrases of layer 2, the ones the model answered right too: a tool of Taxes that a
    new ask elsewhere pushes out of the ones a turn offers fails here before the real-model QA sees it. What the
    employee may not run (``expect: refused``) is not in their catalogue at all."""
    assert (probe["app"], probe["language"]) == ("tax", "es")
    tools = catalog_of(ROLES[probe["role"]], probe["language"])
    name, phrase = probe["tool"], probe["phrase"]
    if probe["expect"] == "refused":
        assert name in TOOLS and name not in tools
        return
    assert_offered_with_room(tools, name, phrase)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "instead"), CHOSEN_INSTEAD)
def test_the_reported_request_offers_its_tool_before_the_switch_of_an_app(catalog_of, name, instead):
    tools = catalog_of(Membership.Role.OWNER, "es")
    offered = [op.name for op in assistant.relevant(tools, [dict(REPORTED)[name]], "es")]
    assert instead in tools  # positive control: what comes ahead is a tool of the owner too
    assert name in offered, offered[:10]
    assert instead not in offered or offered.index(name) < offered.index(instead), offered[:10]


def test_every_tool_of_taxes_has_its_own_words():
    assert [name for name, _ in OWN_WORDS] == list(dict.fromkeys(name for name, _ in OWN_WORDS))  # one each
    assert {name for name, _ in OWN_WORDS} == TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(catalog_of, name, phrase):
    assert_its_asks_bring(catalog_of(Membership.Role.OWNER, "es"), name, phrase, "es")
