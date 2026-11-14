"""What layer 1 of the assistant's QA does not say of Payments: how many tools it offers, what an employee is never
offered, that the real-model QA's requests (hub#1090), in the owner's and the employee's own words, are offered their
existing operation, and that a payment to a supplier is never taken for a charge of the till, nor the other way round.
And what the Hub's words of Payments are for (a «cuenta bancaria» or «del banco» is a Payments' method,
``base.assistant.SYNONYMS``), and that each tool's asks, not only its name, bring what a person says in words of their
own.

Every ask of every tool of payment bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (payment is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over
the asks and the guard that no ask copies a probe of layer 2.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import TOP, assert_its_asks_bring, assert_offered_with_room, comparable, offered_to
from base.tests.test_assistant_asks import place_in, probe_phrases
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

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
#: The tender of the till a Payments' method tool can be taken for: the same action on how a customer pays (the model
#: read the till's list for «¿desde qué cuentas pago a proveedores?»). The till lists and adds its tenders and nothing
#: else, so Payments' get, update, activate and deactivate have none: their probes are only to be offered.
TENDER_OF = {"payment.method.list": "sale.payment_method.list", "payment.method.create": "sale.payment_method.create"}
#: The requests of the till's tenders of Sales' QA (``owner-es-sale-*.json``, ``sale-customer-base.json``), as the
#: owner said them: Payments' methods, now that they say their asks, never go ahead of them.
TENDERS = [
    probe
    for path in sorted((Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes").glob("*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    if probe["tool"].startswith(TILLS) and probe["language"] == "es" and probe["role"] == "owner"
]


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
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, "es"), name, phrase)


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
    assert_offered_with_room(tools, name, phrase)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    "probe",
    [probe for probe in PROBES if probe["tool"] in TENDER_OF and probe["expect"] != "refused"],
    ids=lambda probe: probe["id"],
)
def test_where_the_business_pays_a_supplier_from_goes_ahead_of_the_tills_tender(catalog_of, probe):
    """«¿Desde qué cuentas pago a proveedores?» is Payments' method, never how a customer pays at the till: the model
    read ``sale.payment_method.list`` because it came first. Each request to list or add a Payments' method puts it
    ahead of the till's tender of the same action."""
    offered = offered_to(catalog_of(ROLES[probe["role"]], "es"), probe["phrase"])
    tender = TENDER_OF[probe["tool"]]
    assert tender in offered  # positive control: the tender competes in the ranking
    mine = place_in(offered, probe["tool"]) or len(offered) + 1  # not offered: behind the tender
    assert mine < place_in(offered, tender), (mine, place_in(offered, tender))


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", TENDERS, ids=lambda probe: f"{probe['id']}")
def test_a_tender_of_the_till_is_never_taken_for_where_the_business_pays_its_suppliers_from(catalog_of, probe):
    """The other way round: how a customer pays at the till (Sales' probes) never puts a Payments' method ahead of the
    till's tender it asks for, whatever place the tender itself has."""
    offered = offered_to(catalog_of(Membership.Role.OWNER, "es"), probe["phrase"])
    outgoing = [place_in(offered, name) for name in offered if name.startswith(OUTGOING)]
    tender = place_in(offered, probe["tool"]) or len(offered) + 1
    assert all(tender < at for at in outgoing), (tender, outgoing)


#: live reads «habilitar» and «activar» as the action ``activate`` of a tool too, not only as turning something on
#: (``enable``, an app's ``base.app.enable``), so the request to bring Banco QA back is offered ahead of turning an app
#: on.
@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_reported_request_to_bring_a_method_back_goes_ahead_of_turning_an_app_on(catalog_of):
    offered = offered_to(catalog_of(Membership.Role.OWNER, "es"), dict(REPORTED)["payment.method.activate"])
    assert "base.app.enable" in offered  # positive control: turning an app on competes in the ranking
    assert place_in(offered, "payment.method.activate") < place_in(offered, "base.app.enable"), offered[:10]


#: Where the business pays from in the Hub's words (``base.assistant.SYNONYMS``): a «cuenta bancaria» or «cuenta del
#: banco», never the table's check a «cuenta» alone is, and a «bank account», are a Payments' method, as «method» is.
BANK_ACCOUNT = (
    "cuenta bancaria", "cuentas bancarias", "cuenta del banco", "cuentas del banco", "bank account", "bank accounts",
)
#: In phrases nobody wrote as asks nor as probes, each brings its tool among the first ten, and none does without them:
#: in Spanish and in English, so the «bank account» of the group is held by what a turn offers and not only by how
#: the words read. Language, tool, phrase.
PAYMENT_WORDS = [
    ("es", "payment.method.list", "¿qué cuentas bancarias tenemos?"),
    ("es", "payment.method.update", "cambia la referencia de la cuenta del banco"),
    ("en", "payment.method.update", "the bank account of BBVA has a new number"),
]


@pytest.mark.parametrize("words", BANK_ACCOUNT)
def test_the_hub_reads_a_bank_account_as_where_the_business_pays_from(words):
    phrase = f"la {words} del BBVA"
    method = shared.asked(["the payment method"]).concepts
    assert any("metho" in concept for concept in method)  # positive control: «method» names Payments' method
    assert any("metho" in concept for concept in shared.asked([phrase], assistant.SYNONYMS).concepts), phrase
    assert not any("metho" in concept for concept in shared.asked([phrase]).concepts), phrase


def without_the_bank_account():
    """The Hub's ``SYNONYMS`` without the group of where the business pays from."""
    kept = tuple(group for group in assistant.SYNONYMS if not set(BANK_ACCOUNT) & set(group))
    assert len(kept) == len(assistant.SYNONYMS) - 1  # positive control: the group is there, and only one
    return kept


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "name", "phrase"), PAYMENT_WORDS)
def test_a_bank_account_said_by_its_name_brings_the_payments_method(catalog_of, language, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, language)
    offered = offered_to(tools, phrase, language)
    assert name in offered[:TOP], (place_in(offered, name), offered[:TOP])
    unnamed = offered_to(tools, phrase, language, synonyms=without_the_bank_account())
    assert name not in unnamed[:TOP], place_in(unnamed, name)


#: What a person says in words of their own, neither an ask nor a probe of layer 2 (nor an ask with a word changed), one
#: per tool: it is their asks that bring each among the first ten (``assert_its_asks_bring``), so asks that stop
#: reading as people speak fail. Language, tool, phrase.
OWN_WORDS = [
    ("en", "payment.payment.list", "which transfers to suppliers are still waiting?"),
    ("en", "payment.payment.get", "I need the IBAN the Iberdrola money went to"),
    ("es", "payment.method.list", "¿por dónde salen los pagos que hacemos a proveedores?"),
    ("es", "payment.method.get", "necesito la referencia del Santander para dársela a un proveedor"),
    ("es", "payment.method.create", "queremos pagar a proveedores desde el Santander, que aún no está"),
    ("es", "payment.method.update", "el número de la cuenta bancaria del BBVA ha cambiado"),
    ("en", "payment.method.deactivate", "stop the old BBVA account from being used"),
    ("en", "payment.method.activate", "we can pay from the BBVA bank account again"),
    ("en", "payment.payment.create", "write down what we owe Iberdrola, 300 €, without moving money"),
    ("es", "payment.payment.approve", "da el visto bueno al borrador de Iberdrola"),
    ("es", "payment.payment.mark_sent", "la transferencia de Iberdrola ya la mandé desde el banco"),
    ("es", "payment.payment.mark_completed", "Iberdrola dice que ya tiene el dinero"),
    ("es", "payment.payment.cancel", "lo de Iberdrola ya se pagó en efectivo, esa transferencia sobra"),
]


def test_each_tool_of_payments_has_its_own_words():
    assert sorted(name for _, name, _ in OWN_WORDS) == sorted(
        name for name, op in registry.items() if op.app_label == "payment" and assistant.is_tool(op)
    )


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "name", "phrase"), OWN_WORDS, ids=[name for _, name, _ in OWN_WORDS])
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(catalog_of, language, name, phrase):
    assert_its_asks_bring(catalog_of(Membership.Role.OWNER, language), name, phrase, language)
