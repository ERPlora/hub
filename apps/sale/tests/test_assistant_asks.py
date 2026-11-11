"""What layer 1 of the assistant's QA does not say of Sales & POS (erplora-next docs plan 2026-10-31, the assistant's
knowledge and QA): how many phrases its tools put to a turn, and what each role is never offered.

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
from base.tests.test_assistant_asks import TOP, alike, comparable, probe_phrases, without_its_asks

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


#: The requests of the QA of hub#1085, each as a person says it: a record of the QA's data names what it is («the
#: QA Sweets section»), as no selection knows a bare name («Chuches QA») without the business's data.
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
    ("es", "sale.department.update", "Renombra la sección Chuches QA a Golosinas QA y ordénala la primera"),
    ("en", "sale.department.update", "Rename the QA Sweets section to QA Candy and reorder it first"),
    ("es", "sale.quick_note.update", "Renombra la nota Sin cilantro QA"),
    ("en", "sale.quick_note.update", "Rename the No cilantro QA note"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "name", "phrase"), QA_PROBES)
def test_the_reported_sales_request_offers_its_existing_operation(language, name, phrase):
    tools = assistant.catalog(ctx_for("hub_owner", language=language))
    assert name in tools
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered[:10]


#: Undoing a line's voucher in words that are no ask nor probe: ``sale.order.remove_voucher``'s asks bring it among the
#: first ten (with them, 4th in Spanish and 7th in English); without them it falls out (33rd, and out of the ones a turn
#: offers). Its asks no longer say the QA's «quita el bono de la línea» with one word changed (hub#1135).
OWN_WORDS = [
    ("es", "sale.order.remove_voucher", "no lo uses en esta cuenta, mejor lo guarda"),
    ("en", "sale.order.remove_voucher", "she would rather not use it on the haircut"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "name", "phrase"), OWN_WORDS)
def test_a_voucher_undone_in_the_persons_own_words_reaches_its_tool_by_its_asks(language, name, phrase):
    tools = assistant.catalog(ctx_for("hub_owner", language=language))
    assert name in tools  # positive control: the owner holds it, so its place is known
    assert comparable(phrase) not in probe_phrases()
    assert not [ask for said in asks_of(tools[name]).values() for ask in said if alike(ask, phrase)]
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered[:TOP], (offered.index(name) + 1 if name in offered else None, offered[:TOP])
    unasked = [op.name for op in assistant.relevant(without_its_asks(tools, name), [phrase], language)]
    assert name not in unasked[:TOP]  # what brings it is its asks, so a change to them is seen here


def test_no_qa_probe_is_an_ask():
    """The probes measure that the selection generalises (erplora-next docs plan 2026-10-31 §1.5): a probe copied into
    the asks of its tool ranks its own words, layer 2 skips it as a copy of an ask, and a record of the QA's data
    («Cuenta QA», «Chuches QA») is no phrase a business says."""
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
