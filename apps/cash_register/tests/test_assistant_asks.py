"""What layer 1 of the assistant's QA does not say of Cash register (docs plan 2026-10-31, the assistant's knowledge and
QA, §3): how many tools it offers, and that the requests of the real-model QA (hub#1087), in the words the person said
them, are offered their existing operation, and with it the read it needs first.

Every ask of every tool of cash_register bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (cash_register is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020``
over the asks and the guard that no ask copies a probe of layer 2.
"""

import pytest
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tests.test_assistant_asks import comparable, probe_phrases

A = Scope("host", "a")
OWNER, EMPLOYEE = Membership.Role.OWNER, Membership.Role.EMPLOYEE

#: The requests of hub#1087's QA (``tests/e2e/qa/probes/*-es-cash_register-2026-11-08.json``), as each role said them:
#: before Cash register said its asks, the first four were offered no tool of the drawer (the model answered it had no
#: tool, or looked for an automation) and the print was offered without the read that finds the open shift (the model
#: asked for the session's number). The employee's close was already offered (4th), its summary too: what the model did
#: after reading the summary is layer 2's to measure again.
REPORTED = [
    (OWNER, "cash_register.count.list", "¿qué recuentos de monedas y billetes se han registrado en el turno abierto?"),
    (
        OWNER,
        "cash_register.session.get",
        "pásame el informe completo del turno abierto, con fondo, ventas, movimientos y diferencia",
    ),
    (
        OWNER,
        "cash_register.count.add",
        "registra un recuento de apertura en Barra QA: tres billetes de 50 € y veinte monedas de 1 €, con nota "
        "«comprobado QA»",
    ),
    (
        OWNER,
        "cash_register.session.auto_close",
        "ejecuta ahora el cierre automático diario por si hubiera algún turno antiguo que ya hubiera pasado la hora de "
        "corte",
    ),
    (
        OWNER,
        "cash_register.session.print",
        "imprime el informe X del turno abierto de Barra QA con las ventas y los movimientos hasta ahora",
    ),
    (
        EMPLOYEE,
        "cash_register.session.close",
        "cierra la sesión S-261109-0001 con 170 € contados y la nota «cierre de empleado QA», mostrándome antes el "
        "resumen",
    ),
]
#: The read each reported request needs before its tool: a session said as «el turno abierto» is found by
#: ``cash_register.session.current`` (the report, its counts and its print take the session's id or number), and the
#: close is said after ``cash_register.session.closing_summary`` (its description asks to read it first).
FIRST = {
    "cash_register.count.list": "cash_register.session.current",
    "cash_register.session.get": "cash_register.session.current",
    "cash_register.session.print": "cash_register.session.current",
    "cash_register.session.close": "cash_register.session.closing_summary",
}
#: The role of a probe as its id says it (``qa20261108.<role>.es.<tool>``).
PROBE_ROLE = {OWNER: "owner", EMPLOYEE: "employee"}


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def test_cash_register_offers_at_least_19_tools():
    """Cash register's tools are at least 19 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "cash_register" and isinstance(op.ai_spec(), AI)}
    assert len(tools) >= 19


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, _, phrase in REPORTED] == [
        f"qa20261108.{PROBE_ROLE[role]}.es.{name}" for role, name, _ in REPORTED
    ]


def test_the_hub_reads_an_arqueo_as_a_count_and_the_moneda_as_the_currency():
    """``base.assistant.SYNONYMS``: an «arqueo», a «recuento» or a «conteo» is a count of the drawer
    (``cash_register.count``) and the «moneda» or the «divisa» of the business its currency (``cash_register.currency``),
    so the person's words reach those tools without their own asks; without the Hub's groups, none does (positive
    control)."""
    count, currency = shared.stem("count"), shared.stem("currency")
    for phrase, wanted in (
        ("haz el arqueo del cajón", count),
        ("¿hay algún recuento de cierre?", count),
        ("apunta el conteo de la mañana", count),
        ("¿en qué moneda trabaja el negocio?", currency),
        ("¿cuál es la divisa del negocio?", currency),
    ):
        concepts = shared.asked([phrase], assistant.SYNONYMS).concepts
        assert any(wanted in concept for concept in concepts), phrase
        assert not any(wanted in concept for concept in shared.asked([phrase]).concepts), phrase


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize(("role", "name", "phrase"), REPORTED)
def test_the_reported_cash_register_request_offers_its_existing_operation(catalog_of, role, name, phrase):
    tools = catalog_of(role, language := "es")
    assert name in tools  # positive control: the role holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get(language, ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered, (len(offered), offered[:10])


@pytest.mark.django_db
@pytest.mark.parametrize(("role", "name", "phrase"), [case for case in REPORTED if case[1] in FIRST])
def test_the_reported_request_is_offered_the_read_it_needs_first(catalog_of, role, name, phrase):
    tools = catalog_of(role, "es")
    assert FIRST[name] in tools  # positive control: the role holds the read
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert FIRST[name] in offered, (len(offered), offered[:10])
