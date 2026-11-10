"""What layer 1 of the assistant's QA says of Printing (erplora-next docs/plans/2026-10-31-asistente-conocimiento-y-qa.md):
how many tools it offers, and the two writes the real-model QA found unreachable (hub#1086).

Every ask of every tool of printing bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(printing is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""

import pytest
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")
#: What only who runs the business does: an employee's assistant is never offered the printers' settings.
NOT_THE_EMPLOYEES = {
    "printing.printer.create",
    "printing.printer.update",
    "printing.settings.update",
    "printing.device.register",
    "printing.device.retire",
}
WITH_ROOM = 7
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


#: The phrases of the real-model QA (``qa20261108.owner.es.printing.printer.*``, hub#1086), in words that are none of the
#: tools' ``asks``: neither tool was among the ones offered, so the model answered it had no tool.
QA_PHRASES = [
    (
        "es",
        "printing.printer.test",
        "saca una página de prueba en la impresora Caja QA",
        WITH_ROOM,
    ),
    (
        "en",
        "printing.printer.test",
        "print a test page on the Caja QA printer",
        WITH_ROOM,
    ),
    (
        "es",
        "printing.printer.update",
        "cambia la IP, el papel y el nombre de la impresora Caja QA",
        WITH_ROOM,
    ),
    (
        "en",
        "printing.printer.update",
        "change the IP, the paper and the name of the Caja QA printer",
        WITH_ROOM,
    ),
    (
        "es",
        "printing.device.list",
        "¿qué equipos hay registrados para imprimir los tickets del negocio?",
        TOP,
    ),
    (
        "en",
        "printing.device.list",
        "which devices are registered to print the business's tickets?",
        TOP,
    ),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "name", "phrase", "bound"), QA_PHRASES)
def test_the_reported_printing_asks_bring_their_tool_among_the_first_places(
    catalog_of, language, name, phrase, bound
):
    tools = catalog_of(Membership.Role.OWNER, language)
    assert (
        name in tools
    )  # positive control: the owner holds it, so the model can receive it
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered[:bound], (
        offered.index(name) + 1 if name in offered else None,
        offered[:bound],
    )
