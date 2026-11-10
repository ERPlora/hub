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
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tests.test_assistant_asks import comparable, probe_phrases

A = Scope("host", "a")
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


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


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
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:10])


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
    assert name in tools  # positive control: the role holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:10])
