"""What layer 1 of the assistant's QA does not say of Payments (docs plan 2026-10-31, the assistant's knowledge and QA,
§3): how many tools it offers, what an employee is never offered, that the real-model QA's requests (hub#1090), in the
owner's and the employee's own words, are offered their existing operation, and that a payment to a supplier is never
taken for a charge of the till, nor the other way round.

Every ask of every tool of payment bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (payment is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over
the asks and the guard that no ask copies a probe of layer 2.
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
#: Every write of Payments: an employee only looks (``payment.view_payment``), and none of them is a write a manager
#: approves, so an employee's assistant is never offered them and answers it has no permission (``expect: refused``).
NOT_THE_EMPLOYEES = {
    "payment.method.create",
    "payment.method.update",
    "payment.method.deactivate",
    "payment.method.activate",
    "payment.payment.create",
    "payment.payment.approve",
    "payment.payment.mark_sent",
    "payment.payment.mark_completed",
    "payment.payment.cancel",
}

#: The owner's requests of hub#1090's QA (``tests/e2e/qa/probes/owner-es-payment-2026-11-08.json``) as they were said,
#: and nothing of the tools' ``asks``: before Payments said its asks, five of these tools were not among the ones a turn
#: offers (``MAX_TOOLS``) and the sixth, the payment marked as sent, 28th, so the model read the till's tenders
#: (``sale.payment_method.list``), said it could not approve or had no tool, or sent the owner to the screen.
REPORTED = [
    ("payment.method.get", "enséñame la referencia completa de la cuenta Banco QA y si admite nuevos pagos"),
    ("payment.method.list", "¿desde qué cuentas, tarjetas o cajones puedo registrar pagos a proveedores?"),
    ("payment.payment.approve", "autoriza el borrador de 42,75 € a Proveedor QA para que ya pueda tramitarse"),
    (
        "payment.payment.mark_sent",
        "he ordenado en el banco el pago a Proveedor QA; marca ese pago como enviado, sin hacer ninguna transferencia "
        "desde aquí",
    ),
    ("payment.method.deactivate", "impide que Banco QA se use en pagos nuevos, sin borrar los movimientos que ya tiene"),
    ("payment.method.activate", "vuelve a habilitar Banco QA para registrar pagos salientes"),
]

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a request of the QA may bring its tool: half of them, so
#: the apps that say their asks later may push it down before the model loses it.
WITH_ROOM = 20
#: Every probe of layer 2 of Payments, the owner's and the employee's real phrases of the QA: the six above and the ones
#: the model got right, or refused as it should.
PROBES = [
    probe
    for path in sorted((Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes").glob("*-es-payment-*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
]
ROLES = {"owner": Membership.Role.OWNER, "employee": Membership.Role.EMPLOYEE}
#: The tenders of the till (Sales' payment methods: how a customer pays), never where the business pays its suppliers
#: from (Payments' methods); «cobra» and «cobro» are a sale's.
TILLS = ("sale.payment_method.",)
OUTGOING = ("payment.method.",)
#: The requests of the till's tenders of Sales' QA (``owner-es-sale-*.json``, ``sale-customer-base.json``), as the
#: owner said them: Payments' methods, now that they say their asks, never go ahead of them.
TENDERS = [
    probe
    for path in sorted((Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes").glob("*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    if probe["tool"].startswith(TILLS) and probe["language"] == "es" and probe["role"] == "owner"
]


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def offered_to(tools: dict[str, Operation], phrase: str) -> list[str]:
    return [op.name for op in assistant.relevant(tools, [phrase], "es")]


def place(offered: list[str], name: str) -> int | None:
    return offered.index(name) + 1 if name in offered else None


def test_payment_offers_its_thirteen_tools():
    """Payments' tools are its thirteen operations (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "payment" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) == 13


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_an_employee_is_never_offered_a_write_of_payments(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert "payment.payment.list" in employee  # positive control: an employee looks at the payments


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"qa20261108.owner.es.{name}" for name, _ in REPORTED
    ]
    assert {probe["tool"] for probe in PROBES} >= {name for name, _ in REPORTED}  # the probes below include them
    assert len(TENDERS) >= 3  # positive control: Sales' probes of the till's tenders are read


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_payment_request_offers_its_existing_operation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = offered_to(tools, phrase)
    assert name in offered[:WITH_ROOM], (place(offered, name), offered[:10])


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_payments_offers_its_tool_or_is_refused_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's thirteen phrases and the employee's six of layer 2: what the role holds is offered in the first half
    of a turn's tools, and what it may not do is not in its catalogue at all (the model answers it has no permission);
    a tool of Payments that a new ask elsewhere pushes down fails here before the real-model QA sees it."""
    assert (probe["app"], probe["language"]) == ("payment", "es")
    tools = catalog_of(ROLES[probe["role"]], "es")
    name, phrase = probe["tool"], probe["phrase"]
    if probe["expect"] == "refused":
        assert name in NOT_THE_EMPLOYEES and name not in tools
        return
    assert name in tools  # positive control: the role holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = offered_to(tools, phrase)
    assert name in offered[:WITH_ROOM], (place(offered, name), offered[:10])


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    "probe",
    [probe for probe in PROBES if probe["tool"].startswith(OUTGOING) and probe["expect"] != "refused"],
    ids=lambda probe: probe["id"],
)
def test_where_the_business_pays_a_supplier_from_goes_ahead_of_the_tills_tenders(catalog_of, probe):
    """«¿Desde qué cuentas pago a proveedores?» is Payments' method, never how a customer pays at the till: the model
    read ``sale.payment_method.list`` because it came first. Each request of a Payments' method puts it ahead of every
    tender of the till the turn offers."""
    offered = offered_to(catalog_of(ROLES[probe["role"]], "es"), probe["phrase"])
    tills = [place(offered, name) for name in offered if name.startswith(TILLS)]
    mine = place(offered, probe["tool"]) or len(offered) + 1  # not offered: behind every tender offered
    assert all(mine < at for at in tills), (mine, tills)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", TENDERS, ids=lambda probe: f"{probe['id']}")
def test_a_tender_of_the_till_is_never_taken_for_where_the_business_pays_its_suppliers_from(catalog_of, probe):
    """The other way round: how a customer pays at the till (Sales' probes) never puts a Payments' method ahead of the
    till's tender it asks for, whatever place the tender itself has."""
    offered = offered_to(catalog_of(Membership.Role.OWNER, "es"), probe["phrase"])
    outgoing = [place(offered, name) for name in offered if name.startswith(OUTGOING)]
    tender = place(offered, probe["tool"]) or len(offered) + 1
    assert all(tender < at for at in outgoing), (tender, outgoing)
