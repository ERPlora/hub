"""What layer 1 of the assistant's QA says of Printing (erplora-next docs/plans/2026-10-31-asistente-conocimiento-y-qa.md):
how many tools it offers, and the two writes the real-model QA found unreachable (hub#1086).

Every ask of every tool of printing bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(printing is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""

import re
import unicodedata

import pytest
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tests.test_assistant_asks import assert_its_asks_bring

A = Scope("host", "a")
#: What only who runs the business does: an employee's assistant is never offered the printers' settings.
NOT_THE_EMPLOYEES = {
    "printing.printer.create",
    "printing.printer.update",
    "printing.settings.update",
    "printing.device.register",
    "printing.device.retire",
}
#: The first ten places a turn offers, the bound of the QA (``base/tests/test_assistant_asks.py``).
TOP = 10


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(
            scope=A,
            actor=user.username,
            permissions=permissions_for(user, A),
            language=language,
        )
        return assistant.catalog(ctx)

    return of


def test_printing_offers_at_least_20_tools():
    """Printing's tools are at least 20 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {
        name
        for name, op in registry.items()
        if op.app_label == "printing" and isinstance(op.ai_spec(), AI)
    }
    assert len(tools) >= 20


@pytest.mark.django_db
def test_an_employee_is_never_offered_the_printers_settings(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert (
        "printing.printer.test" in employee
    )  # positive control: printing is the employee's own door


#: The requests of hub#1086's QA as the person said them (``tests/e2e/qa/probes/*-es-printing-2026-11-08.json``), with
#: the role that said each, and nothing of the tools' ``asks``: before Printing said its asks, none of these tools was
#: among the ones a turn offers (``MAX_TOOLS``), so the model answered it had no tool. Now a turn offers all of them
#: (measured on this branch: the test page 16th, the printer change 25th, the employee's devices 9th): the model can
#: choose them, and their words stay the person's, never the asks'
#: (``test_no_ask_copies_a_qa_probe_or_names_a_qa_record``).
REPORTED = [
    (
        Membership.Role.OWNER,
        "printing.printer.test",
        "saca una página de prueba en Caja QA para comprobar la conexión y el papel",
    ),  # qa20261108.owner.es.printing.printer.test
    (
        Membership.Role.OWNER,
        "printing.printer.update",
        "cambia Caja QA a la IP 192.168.1.241, papel de 58 mm y renómbrala «Caja barra QA»",
    ),  # qa20261108.owner.es.printing.printer.update
    (
        Membership.Role.EMPLOYEE,
        "printing.device.list",
        "¿qué equipos hay registrados para imprimir los tickets del negocio?",
    ),  # qa20261108.employee.es.printing.device.list
]


def comparable(text: str) -> str:
    """``text`` as layer 2 compares a probe with the asks: lower case, without accents, punctuation or extra spaces."""
    bare = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w]+|_", " ", bare).split())


@pytest.mark.django_db
@pytest.mark.parametrize(("role", "name", "phrase"), REPORTED)
def test_the_reported_printing_requests_are_offered_their_tool_without_being_its_asks(catalog_of, role, name, phrase):
    tools = catalog_of(role, language := "es")
    assert name in tools  # positive control: the role holds it, so the model can receive it
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get(language, ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered, offered


#: A device that prints, retired in words that are no ask nor probe and that only its tool's asks bring among the first
#: ten: «dispositivo» is the Hub's own word for it (Printing → Devices, «Dispositivo 1»). Since ERPlora/live#64,
#: «retira» asks to retire, delete, remove and withdraw, and «el equipo» reads as the staff
#: (``live.assistant.SYNONYMS``), so an ask that said «retira el equipo Barra 2» fell to the edge of the ten (10th) and
#: this phrase with it (13th). With «el dispositivo» in the ask it is 8th for the owner, the admin and the manager, and
#: 13th without its asks.
OWN_WORDS = [
    ("es", "printing.device.retire", "el dispositivo Terraza 1 ya no está, que no imprima más"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER])
@pytest.mark.parametrize(("language", "name", "phrase"), OWN_WORDS)
def test_a_retired_device_in_the_persons_own_words_reaches_its_tool_by_its_asks(
    catalog_of, role, language, name, phrase
):
    assert_its_asks_bring(catalog_of(role, language), name, phrase, language)
