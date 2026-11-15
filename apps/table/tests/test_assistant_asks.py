"""What layer 1 of the assistant's QA does not say of Tables: how many tools and phrases it offers, what an employee is
never offered, and the requests of the real-model QA that came back without their tool (hub#1081).

Every ask of every tool of table bringing its tool among the first ten, role by role, in English and in Spanish, out of
the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(table is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""

import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from live.assistant import asks_of
from live.operations import registry

from base import assistant
from base.tests.test_assistant_asks import offered_to

from .conftest import ctx_for

LANGUAGES = ("en", "es")
#: Table's tools (``AI``, never ``INTERNAL``): a silent drop of tools fails.
MIN_TOOLS = 33
#: The phrases of table's tools put to the turn at least, both languages together: a silent drop of asks fails.
MIN_PHRASES = 160
#: The writes on the room and its settings, and the deletion of a closed check, that no employee holds and no manager
#: approves (``table`` names no ``approvals``): an employee's assistant is never offered them.
NOT_THE_EMPLOYEES = {
    "table.zone.create",
    "table.zone.update",
    "table.zone.delete",
    "table.table.create",
    "table.table.bulk_create",
    "table.table.update",
    "table.table.move",
    "table.table.delete",
    "table.session.delete",
    "table.settings.update",
}


def table_tools() -> list:
    return [op for op in registry.values() if op.app_label == "table" and assistant.is_tool(op)]


def test_table_offers_at_least_33_tools():
    assert len(table_tools()) >= MIN_TOOLS


def test_every_phrase_of_table_is_one_of_at_least_160():
    """Each tool of table says at least two phrases in each language (``live.E020``), three in the ones a waiter asks
    for most; they are at least ``MIN_PHRASES`` in all, so what the layer ranks is the whole set and never a silent
    few."""
    assert sum(len(asks_of(op).get(language, ())) for op in table_tools() for language in LANGUAGES) >= MIN_PHRASES


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_an_employee_is_never_offered_what_only_the_owner_may_do():
    owner = assistant.catalog(ctx_for("hub_owner", language="es"))
    employee = assistant.catalog(ctx_for("hub_employee", language="es"))
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    # Positive control: the employee seats, splits and moves checks, as the floor plan lets them.
    assert {"table.session.open", "table.session.split", "table.session.transfer"} <= set(employee)


#: The requests of the real-model QA of hub#1081 (``tests/e2e/qa/probes/{owner,employee}-es-table-2026-11-08.json``),
#: each with the role that said it, and an English twin nobody wrote as an ask: the tool of Tables that does it was not
#: among the 40 a turn offers (seat, split, guests, transfer), or came 12th and 17th, behind Sales' tools that do
#: something else.
QA_PROBES = [
    ("hub_owner", "es", "table.session.open",
     "sienta a dos personas en la mesa 3 de Comedor QA y apunta «cumpleaños QA» en la cuenta"),
    ("hub_owner", "en", "table.session.open", "seat two people at table 3 in the QA Dining room and note a birthday"),
    ("hub_owner", "es", "table.session.split",
     "abre una segunda cuenta vacía en la mesa 1 de Comedor QA para una persona que pagará aparte"),
    ("hub_owner", "en", "table.session.split",
     "open a second empty check at table 1 in the QA Dining room for someone paying separately"),
    ("hub_owner", "es", "table.session.set_guests",
     "en la primera cuenta de la mesa 1 de Comedor QA corrige los comensales a tres, ha llegado uno más"),
    ("hub_owner", "en", "table.session.set_guests",
     "on the first check of table 1 in the QA Dining room make it three guests, one more just arrived"),
    ("hub_owner", "es", "table.session.transfer",
     "traslada la segunda cuenta de la mesa 1 de Comedor QA a la mesa 2, con los mismos comensales y notas"),
    ("hub_owner", "en", "table.session.transfer",
     "move the second check of table 1 in the QA Dining room to table 2, same guests and notes"),
    ("hub_owner", "es", "table.session.delete",
     "borra del historial la segunda cuenta que acabo de cerrar en la mesa 1 de Comedor QA, conservando su rastro"),
    ("hub_owner", "en", "table.session.delete",
     "delete from the history the second check I just closed at table 1 in the QA Dining room"),
    ("hub_employee", "es", "table.settings.get", "¿a los cuántos minutos se marca una mesa en amarillo y luego en rojo?"),
    ("hub_employee", "en", "table.settings.get", "after how many minutes does a table turn amber and then red?"),
    ("hub_employee", "es", "table.session.link_order",
     "asocia la Cuenta QA del TPV a la cuenta vacía de la mesa 4 de Comedor QA"),
    ("hub_employee", "en", "table.session.link_order",
     "attach the QA Check from the till to the empty check of table 4 in the QA Dining room"),
]


def offered(role: str, language: str, name: str, phrase: str) -> list[str]:
    tools = assistant.catalog(ctx_for(role, language=language))
    assert name in tools  # positive control: the role holds the tool, so its place is known
    return offered_to(tools, phrase, language)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("role", "language", "name", "phrase"), QA_PROBES)
def test_the_reported_tables_request_offers_its_existing_operation(role, language, name, phrase):
    """Among the ``MAX_TOOLS`` a turn offers, so the model can choose it: its description says when it, and not Sales',
    is the one (``NOT_SALES``)."""
    assert name in offered(role, language, name, phrase)


#: The reported requests that come among the first ten, as layer 1 asks of an ask: «sienta» opens, «traslada»
#: transfers and «comensales» are the guests. Not the Spanish split: «abre una segunda cuenta» asks to
#: open a check, which ``sale.order.open`` does by its very verb, so it is only offered.
WITHIN_TEN = [case for case in QA_PROBES if case[1:3] != ("es", "table.session.split")]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("role", "language", "name", "phrase"), WITHIN_TEN)
def test_the_reported_tables_request_comes_among_the_first_ten(role, language, name, phrase):
    first = offered(role, language, name, phrase)
    assert name in first[:10], (first.index(name) + 1 if name in first else None, first[:10])


#: The layer-2 probes of Tables, every role: each is a phrase nobody wrote as an ask.
PROBES = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"


def table_probes() -> list[dict]:
    return [
        probe
        for path in sorted(PROBES.glob("*-table-*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
        if probe["tool"].startswith("table.")
    ]


def test_no_qa_probe_is_an_ask_and_no_ask_names_a_qa_record():
    """The probes measure that the selection generalises: a probe copied into the asks of its tool ranks its own words,
    layer 2 skips it as a copy of an ask, and a record of the QA's data («Comedor QA», «Cuenta QA») is no phrase a
    business says."""
    probes = table_probes() + [{"tool": name, "phrase": phrase} for _, _, name, phrase in QA_PROBES]
    assert len(probes) > 30  # positive control: the probes of layer 2 are read
    for probe in probes:
        for phrases in asks_of(registry[probe["tool"]]).values():
            assert probe["phrase"] not in phrases, probe
    for op in table_tools():
        for phrases in asks_of(op).values():
            for phrase in phrases:
                assert not re.search(r"\bQA\b", phrase), (op.name, phrase)


#: The tool of Sales the model chose instead of the one of Tables (hub#1081): the description of the one of Tables says
#: that it, and not Sales', is the one that seats, splits or moves a table's check.
NOT_SALES = {
    "table.session.open": ("sale.order.open",),
    "table.session.split": ("sale.order.split", "sale.order.open"),
    "table.session.transfer": ("sale.order.set_label",),
}


@pytest.mark.parametrize(("name", "sales"), NOT_SALES.items())
def test_the_tables_operation_says_it_and_not_the_sales_one_does_it(name, sales):
    description = assistant.description(registry[name])
    for other in sales:
        assert other in description


#: What an operation of Tables takes by its id alone, or by its table when the table holds two checks, and the read
#: that finds it from what a person says: the closed check by its table (``table.session.list``), the second check of a
#: split table (``table.table.get`` lists its open checks), the till's check by its title (``sale.order.list``). The
#: model that knew no such read said it could not see the history, or picked another write (hub#1081).
RESOLUTION_READS = {
    "table.session.delete": ("table.session.list",),
    "table.session.restore": ("table.session.list",),
    "table.session.link_order": ("sale.order.list", "table.table.get"),
    "table.session.set_guests": ("table.table.get",),
    "table.session.transfer": ("table.table.get",),
    "table.session.merge": ("table.table.get",),
    "table.session.split": ("table.table.get", "sale.order.get"),
}


@pytest.mark.parametrize(("name", "reads"), RESOLUTION_READS.items())
def test_the_operation_names_the_reads_that_resolve_human_references(name, reads):
    description = assistant.description(registry[name])
    for read in reads:
        assert read in description
