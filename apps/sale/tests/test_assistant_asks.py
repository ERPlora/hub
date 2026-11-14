"""What layer 1 of the assistant's QA does not say of Sales & POS: how many phrases its tools put to a turn, and what
each role is never offered.

Every ask of every tool of sale bringing its tool among the first ten, role by role, in English and in Spanish, out of
the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(sale is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""

import re

import pytest
from live.assistant import asks_of
from live.operations import registry

from apps.sale.tests.conftest import ctx_for
from base import assistant
from base.tests.test_assistant_asks import assert_its_asks_bring, comparable, offered_place, offered_to, probe_phrases
from base.tests.test_assistant_asks import probes_of_layer_2, without_its_asks

LANGUAGES = ("en", "es")
#: The phrases of sale's tools put to the turn at least, both languages together: a silent drop of asks fails.
MIN_PHRASES = 200


def test_every_phrase_of_sale_is_one_of_at_least_200():
    """Each tool of sale says at least two phrases in each language (``live.E020``); they are at least ``MIN_PHRASES``
    in all, so what the layer ranks is the whole set and never a silent few."""
    sale = [op for op in registry.values() if op.app_label == "sale" and assistant.is_tool(op)]
    assert sum(len(asks_of(op).get(language, ())) for op in sale for language in LANGUAGES) >= MIN_PHRASES


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_what_the_employee_may_not_do_is_not_in_their_catalogue():
    """The till's settings are the manager's (``sale.manage_settings``), and no manager approves them on the spot:
    the employee's turn never offers them, whatever they ask; the figures of the business are not theirs either."""
    employee = assistant.catalog(ctx_for("hub_employee", language="es"))
    manager = assistant.catalog(ctx_for("hub_manager", language="es"))
    for name in ("sale.settings.update", "sale.payment_method.create", "sale.sale.today"):
        assert name in manager  # positive control: the manager holds it
        assert name not in employee
    # A write the employee lacks but a manager approves with their PIN stays theirs, as its button does (BASE-F84).
    assert "sale.sale.void" in employee


#: How the owner asks layer 2 what the till takes: live reads no «abonar» as paying, so nothing in it names
#: the payment methods, while «clientes» names the customers and «caja» the till; only the asks of
#: ``sale.payment_method.list`` bring it, and ahead of them.
PAYING_AT_THE_TILL = ("es", "sale.payment_method.list", "¿de qué maneras pueden abonarme los clientes en caja?")

#: The owner's requests of layer 2 that were not offered their tool, word for word as the probes of
#: ``tests/e2e/qa/probes/owner-es-sale-2026-11-08.json`` say them: the record named by its bare name («Chuches QA»),
#: what the asks of each tool bring among the first ten.
LAYER_2 = [
    ("es", "sale.department.update", "renombra Chuches QA como Golosinas QA y déjala la primera de la lista"),
    ("es", "sale.quick_note.update", "donde pone «Sin cilantro QA» escribe mejor «Nada de cilantro QA»"),
    PAYING_AT_THE_TILL,
]

#: The requests of the real-model QA, each as a person says it: a record of the QA's data names what it is («the
#: QA Sweets section»), as no selection knows a bare name («Chuches QA») without the business's data; and the probes
#: of ``LAYER_2``, said as they are.
QA_PROBES = [
    ("es", "sale.order.split", "Pasa el cruasán de Cuenta QA a otra cuenta"),
    ("en", "sale.order.split", "Move the croissant from QA Check to another check"),
    ("es", "sale.order.add_line", "Añade un café a Cuenta QA"),
    ("en", "sale.order.add_line", "Add a coffee to QA Check"),
    ("es", "sale.order.add_service_line", "Añade Corte QA a la cuenta"),
    ("en", "sale.order.add_service_line", "Add QA Haircut to the check"),
    ("es", "sale.order.add_combo_line", "Añade el Menú QA con sus platos"),
    ("en", "sale.order.add_combo_line", "Add the QA Menu with its dishes"),
    ("es", "sale.order.add_open_line", "Apunta 4,75 € a precio libre en Chuches QA"),
    ("en", "sale.order.add_open_line", "Key in 4.75 euros under QA Sweets"),
    ("es", "sale.order.apply_voucher", "Paga Corte QA con el bono de Ana"),
    ("en", "sale.order.apply_voucher", "Pay for QA Haircut with Ana's voucher"),
    ("es", "sale.order.remove_voucher", "Quita el bono de la línea"),
    ("en", "sale.order.remove_voucher", "Take the voucher off the line"),
    ("es", "sale.order.set_appointment", "Vincula la cita de mañana"),
    ("en", "sale.order.set_appointment", "Link tomorrow's appointment"),
    ("es", "sale.order.set_label", "Cambia el nombre de la cuenta"),
    ("en", "sale.order.set_label", "Change the name of the check"),
    ("es", "sale.order.set_line_staff", "Asigna la línea a Camarera Ventas QA"),
    ("en", "sale.order.set_line_staff", "Assign the line to QA Sales Waiter"),
    ("es", "sale.order.update_line", "Corrige cantidad y nota de los cafés"),
    ("en", "sale.order.update_line", "Correct the quantity and note of the coffees"),
    ("es", "sale.order.void_line", "Anula una línea enviada a cocina"),
    ("en", "sale.order.void_line", "Void a line sent to the kitchen"),
    ("es", "sale.refund.list", "Consulta reembolsos de la venta"),
    ("en", "sale.refund.list", "Check the sale's refunds"),
    ("es", "sale.refund.options", "Consulta qué se puede devolver"),
    ("en", "sale.refund.options", "Check what can be refunded"),
    ("es", "sale.sale.complete_over_limit", "Cobra con 60 % autorizado"),
    ("en", "sale.sale.complete_over_limit", "Charge it with an authorised 60% discount"),
    ("es", "sale.sale.issue_documents", "Emite los documentos pendientes"),
    ("en", "sale.sale.issue_documents", "Issue the pending documents"),
    ("es", "sale.sale.refund", "Devuelve 2 € de la venta"),
    ("en", "sale.sale.refund", "Refund 2 euros of the sale"),
    ("en", "sale.department.update", "Rename the QA Sweets section to QA Candy and reorder it first"),
    ("en", "sale.quick_note.update", "Rename the No cilantro QA note"),
    *LAYER_2,
]


def test_the_reported_requests_of_layer_2_are_its_probes_word_for_word():
    """A paraphrase of a probe («Renombra la sección Chuches QA…») passed while the owner's own words were never
    offered their tool: the cases of ``LAYER_2`` are the probes of their tool, as layer 2 says them."""
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, _, phrase in LAYER_2] == [
        f"qa20261108.owner.es.{name}" for _, name, _ in LAYER_2
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "name", "phrase"), QA_PROBES)
def test_the_reported_sales_request_offers_its_existing_operation(language, name, phrase):
    tools = assistant.catalog(ctx_for("hub_owner", language=language))
    assert name in tools
    assert name in offered_to(tools, phrase, language)[:10]


@pytest.mark.django_db
def test_how_customers_may_pay_at_the_till_brings_the_payment_methods_before_the_customers_and_the_till():
    """«¿De qué maneras pueden abonarme los clientes en caja?» asks for the payment methods of the till: they come among
    the first eight, ahead of every tool of Customers and of Cash register its words name."""
    language, name, phrase = PAYING_AT_THE_TILL
    offered = offered_to(assistant.catalog(ctx_for("hub_owner", language=language)), phrase, language)

    assert name in offered[:8], offered[:10]
    named = [tool for tool in offered if tool.split(".")[0] in ("customer", "cash_register")]
    assert named  # positive control: «clientes» and «caja» bring them
    assert offered.index(name) < offered.index(named[0]), offered[:10]


#: Who asks each probe of layer 2, as ``ctx_for`` names the role.
ROLE_OF = {"owner": "hub_owner", "admin": "hub_admin", "manager": "hub_manager", "employee": "hub_employee"}


@pytest.mark.django_db
def test_the_asks_of_the_payment_methods_of_the_till_take_no_place_from_the_payments_methods():
    """The payment methods of the till are no accounts the business pays its suppliers from (``payment.method.*``):
    each probe of layer 2 of Payments that brings its tool among the first ten brings it at the same place with the
    asks of ``sale.payment_method.list`` as without them."""
    moved = []
    kept = 0
    for probe in probes_of_layer_2():
        if not probe["tool"].startswith("payment.method."):
            continue
        tools = assistant.catalog(ctx_for(ROLE_OF[probe["role"]], language=probe["language"]))
        if probe["tool"] not in tools:
            continue
        said = probe["tool"], probe["phrase"], probe["language"]
        asked = offered_place(tools, *said)
        if asked is None or asked > 10:
            continue
        kept += 1
        unasked = offered_place(without_its_asks(tools, "sale.payment_method.list"), *said)
        if asked != unasked:
            moved.append((probe["id"], unasked, asked))
    assert kept  # positive control: some probe of Payments brings its tool among the first ten
    assert moved == []


#: Requests in words that are no ask nor probe, each brought among the first ten by its tool's asks and out of them
#: without: undoing a line's voucher (``sale.order.remove_voucher``, whose asks no longer say the QA's «quita el bono de
#: la línea» with one word changed); and, for ``sale.department.update`` and ``sale.quick_note.update``, one for each of
#: their asks in each language, which falls out without that ask alone (it shares two of its stems at most, and fewer
#: than half of its own), and the English twins of the probes of ``LAYER_2``; and so for ``sale.payment_method.list``,
#: but for «¿con qué me pueden pagar?», which ``PAYING_AT_THE_TILL`` needs instead (the asks of many other tools say
#: «pueden»), and «¿se puede pagar con Bizum?», which says no word the others do not («Bizum» is in «do we accept
#: Bizum?»).
OWN_WORDS = [
    ("en", "sale.payment_method.list", "would we take an Amex card?"),
    ("en", "sale.payment_method.list", "are cheques from regulars accepted?"),
    ("en", "sale.payment_method.list", "which card could they hand over?"),
    ("en", "sale.payment_method.list", "tourists want to settle up, what else is there?"),
    ("es", "sale.payment_method.list", "¿aceptamos el cheque gourmet?"),
    ("es", "sale.payment_method.list", "¿qué maneras tenemos, además del efectivo?"),
    ("es", "sale.payment_method.list", "¿con qué abonan los turistas normalmente?"),
    ("es", "sale.order.remove_voucher", "no lo uses en esta cuenta, mejor lo guarda"),
    ("en", "sale.order.remove_voucher", "she would rather not use it on the haircut"),
    ("en", "sale.department.update", "soft drinks belong on the standard band"),
    ("en", "sale.department.update", "the Misc heading would look better as Others"),
    ("en", "sale.department.update", "rename Sweets as Candy and put it first in the list"),
    ("en", "sale.department.update", "sweets are cheaper on VAT"),
    ("en", "sale.department.update", "rename Sweets to Candy and leave it first on the list"),
    ("es", "sale.department.update", "los refrescos y demás bebidas, que paguen el tipo general"),
    ("es", "sale.department.update", "«Varios» mejor como «Otros», que suena más claro"),
    ("es", "sale.department.update", "la bollería casera, la primera de todas, junto al mostrador"),
    ("es", "sale.department.update", "que las chuches tributen menos"),
    ("en", "sale.quick_note.update", "the salt one: low sodium, as the doctor asked"),
    ("en", "sale.quick_note.update", "our ice one has to sit right at the top, above the rest"),
    ("en", "sale.quick_note.update", "the lactose one would be clearer as 'dairy free' instead"),
    ("en", "sale.quick_note.update", "swap 'spicy' for 'a bit spicy'"),
    ("en", "sale.quick_note.update", "where it says 'No cilantro' write 'No coriander' instead"),
    ("es", "sale.quick_note.update", "lo de la sal ponlo más suave"),
    ("es", "sale.quick_note.update", "lo del hielo tiene que salir el primero cuando apunto bebidas frías"),
    ("es", "sale.quick_note.update", "que en la de los frutos secos diga «trazas»"),
    ("es", "sale.quick_note.update", "en la de «sin trigo», escribe «sin harina»"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(language, name, phrase):
    assert_its_asks_bring(assistant.catalog(ctx_for("hub_owner", language=language)), name, phrase, language)


def test_no_qa_probe_is_an_ask():
    """The probes measure that the selection generalises: a probe copied into the asks of its tool ranks its own words,
    layer 2 skips it as a copy of an ask, and a record of the QA's data («Cuenta QA», «Chuches QA») is no phrase a
    business says."""
    for language, name, phrase in QA_PROBES:
        assert phrase not in asks_of(registry[name]).get(language, ()), phrase
    for op in registry.values():
        if op.app_label == "sale" and assistant.is_tool(op):
            for phrases in asks_of(op).values():
                for phrase in phrases:
                    assert not re.search(r"\bQA\b", phrase), (op.name, phrase)


RESOLUTION_READS = {
    "sale.order.split": ("sale.order.list", "sale.order.get"),
    "sale.order.add_line": ("sale.order.list",),
    "sale.order.add_service_line": ("sale.order.list",),
    "sale.order.add_combo_line": ("sale.order.list",),
    "sale.order.add_open_line": ("sale.order.list",),
    "sale.order.apply_voucher": (
        "sale.order.list",
        "sale.order.get",
        "service.grant.tender_options",
    ),
    "sale.order.remove_voucher": ("sale.order.list", "sale.order.get"),
    "sale.order.set_appointment": ("sale.order.list", "appointment.appointment.list"),
    "sale.order.set_label": ("sale.order.list",),
    "sale.order.set_line_staff": ("sale.order.list", "sale.order.get", "staff.member.list"),
    "sale.order.update_line": ("sale.order.list", "sale.order.get"),
    "sale.order.void_line": ("sale.order.list", "sale.order.get"),
    "sale.refund.list": ("sale.sale.list",),
    "sale.refund.options": ("sale.sale.list",),
    "sale.sale.complete_over_limit": ("sale.order.list",),
    "sale.sale.issue_documents": ("sale.sale.list",),
    "sale.sale.refund": ("sale.sale.list", "sale.refund.options"),
}


@pytest.mark.parametrize(("name", "reads"), RESOLUTION_READS.items())
def test_the_operation_names_the_reads_that_resolve_human_references(name, reads):
    description = assistant.description(registry[name])
    for read in reads:
        assert read in description
