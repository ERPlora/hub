"""What layer 1 of the assistant's QA does not say of Invoicing (docs plan 2026-10-31, the assistant's knowledge and QA,
§3): how many tools it offers, what an employee and a manager are never offered, that the owner's requests of the
real-model QA (hub#1102), in the owner's own words, are offered their existing operation, that the Hub reads a «pagada»
invoice as a paid one, and that each tool's asks, not only its name, bring what a person says in words of their own.

Every ask of every tool of invoice bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (invoice is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over
the asks and the guard that no ask copies a probe of layer 2. That a write's description never sends the model to
answer in the chat before its card is ``tests/test_guardrails_assistant.py``'s, for every app of the Hub.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import (
    assert_its_asks_bring,
    assert_reported_are_owner_probes,
    context_of,  # noqa: F401 (a fixture: the tests below take it by name)
    place_of_no_ask,
)

#: Invoicing's assistant tools: its reads (invoices, their A4 page and what a sale or a refund has, a manual line's
#: rate, the rectification it would issue, the issuer, the numbering and its series) and its writes (issue by hand or
#: from a sale, replace a ticket, mark paid, print, rectify by hand, from a refund or from a void, the issuer and the
#: series). What only the platform does (the hub of ERPlora's own invoices, the issuer from the account) is
#: ``INTERNAL``.
TOOLS = {
    "invoice.invoice.list",
    "invoice.invoice.get",
    "invoice.invoice.document",
    "invoice.invoice.by_source",
    "invoice.invoice.line_defaults",
    "invoice.invoice.rectification_preview",
    "invoice.refund.get",
    "invoice.issuer.get",
    "invoice.numbering.allocations",
    "invoice.numbering.gaps",
    "invoice.numbering.status",
    "invoice.series.list",
    "invoice.series.get",
    "invoice.series.peek_next",
    "invoice.invoice.create",
    "invoice.invoice.create_from_sale",
    "invoice.invoice.substitute",
    "invoice.invoice.mark_paid",
    "invoice.invoice.print",
    "invoice.invoice.rectify",
    "invoice.invoice.rectify_from_refund",
    "invoice.invoice.rectify_from_void",
    "invoice.issuer.update",
    "invoice.series.create",
    "invoice.series.update",
}
#: What rectifies an invoice or decides how the documents are numbered and who issues them (``invoice.rectify_invoice``,
#: ``invoice.manage_series``, ``invoice.manage_issuer``; WORKBOOK «Quién puede qué»), none of them a write a manager
#: approves: an employee's assistant is never offered them, as the screens give an employee no «Rectificar», no series
#: and no issuer.
NOT_THE_EMPLOYEES = {
    "invoice.invoice.rectification_preview",
    "invoice.invoice.rectify",
    "invoice.invoice.rectify_from_refund",
    "invoice.invoice.rectify_from_void",
    "invoice.issuer.update",
    "invoice.series.create",
    "invoice.series.update",
}
#: The issuer is set by who runs the business and an administrator only (``invoice.manage_issuer``).
NOT_THE_MANAGERS = {"invoice.issuer.update"}

#: The owner's requests of hub#1102's QA (``tests/e2e/qa/probes/owner-es-invoice-2026-11-08.json``) as they were said,
#: and nothing of the tools' ``asks``: before Invoicing said its asks, marking an invoice paid and replacing a ticket
#: were not among the tools a turn offers (``MAX_TOOLS``), so the model found the invoice and said it could not mark
#: it, and the rectification was offered fifth, behind its preview.
REPORTED = [
    (
        "invoice.invoice.mark_paid",
        "marca como cobrada la factura de Cliente Factura QA, sin tocar caja ni cambiar importes",
    ),
    (
        "invoice.invoice.rectify",
        "rectifica la factura de Cliente Factura QA con una R1 porque el precio estaba equivocado",
    ),
    (
        "invoice.invoice.substitute",
        "convierte el tique de la venta 20261109-0001 en factura completa para Ana QA, con NIF 12345678Z y Calle "
        "Mayor 1",
    ),
]
#: How far down the tools a turn offers (``MAX_TOOLS``, 40) any request of the QA may bring its tool: half of them, so
#: twenty tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
#: How far down the tools a turn offers the requests hub#1102 is about bring theirs: among the first eight, the three
#: ``ALWAYS`` in front, so the model sees the write it was asked for near the top and calls it.
NEAR_THE_TOP = 8
#: What live reads of «sin tocar caja ni cambiar importes»: the «cambiar» after «ni» as asked (only the infinitive right
#: after «sin» is not, ERPlora/live#60), so the writes that change something go ahead of marking the invoice paid: 12th,
#: and 5th once «ni» reads as «sin». Strict, so the pointer of live that reads it turns this red and its mark goes.
UNTIL_LIVE_READS_NI = pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="ERPlora/live#74: «ni cambiar» after «sin …» reads as asked to change"
)
#: The requests hub#1102 is about, each with its tool: the owner's words of the issue («marca como cobrada la
#: FACT-2026-000001», «rectifícala con una R1») and the two probes of the QA it reports.
THE_ISSUES = [
    pytest.param("invoice.invoice.mark_paid", "marca como cobrada la FACT-2026-000001", id="mark_paid-said"),
    pytest.param("invoice.invoice.rectify", "rectifícala con una R1", id="rectify-said"),
    pytest.param(*REPORTED[0], marks=UNTIL_LIVE_READS_NI, id="mark_paid-probe"),
    pytest.param(*REPORTED[1], id="rectify-probe"),
]
#: Every probe of layer 2 of Invoicing, the owner's real phrases of the QA: the three above and the ones the model got
#: right, some of them 22nd to 40th before Invoicing said its asks.
PROBES = [
    probe
    for path in sorted((Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes").glob("*-es-invoice-*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
]
ROLES = {"owner": Membership.Role.OWNER, "employee": Membership.Role.EMPLOYEE}

#: A paid invoice in the Hub's words (``base.assistant.SYNONYMS``): «pagada» or «pagado», as «paid», and one marked
#: «como cobrada», by its phrases; «cobrar» and «cobro» alone stay a sale's charge (live's own group of a sale).
PAID = (
    "pagada", "pagadas", "pagado", "pagados", "paid", "como cobrada", "como cobradas", "como cobrado", "como cobrados",
)

#: What a person says in words of their own, neither an ask nor a probe of layer 2 (nor an ask with a word changed), one
#: per tool and language: it is their asks that bring each among the first ten (``assert_its_asks_bring``), so asks
#: that stop reading as people speak fail. None shares more than two stems with any one ask or probe of its tool, nor
#: half of its own. Language, tool, phrase.
OWN_WORDS = [
    ("es", "invoice.invoice.list", "busca lo que le hemos emitido a Talleres Mercedes"),
    ("en", "invoice.invoice.list", "anything still pending from Talleres Mercedes?"),
    ("es", "invoice.invoice.get", "quiero ver por dentro la FACT-2025-000412"),
    ("en", "invoice.invoice.get", "read me FACT-2025-000412 from top to bottom"),
    ("es", "invoice.invoice.document", "¿cómo se ve en hoja lo que le dimos a Talleres Mercedes?"),
    ("en", "invoice.invoice.document", "how does the sheet we handed to Talleres Mercedes look?"),
    ("es", "invoice.invoice.by_source", "lo que vendimos esta mañana en la 20261111-0007, ¿con qué papel quedó?"),
    ("en", "invoice.invoice.by_source", "this morning's 20261111-0007: which paper did it end up with?"),
    ("es", "invoice.invoice.line_defaults", "si meto a mano una línea de unas gafas, ¿qué porcentaje le sale?"),
    ("en", "invoice.invoice.line_defaults", "typing glasses in manually, what percentage would you put on them?"),
    (
        "es",
        "invoice.invoice.rectification_preview",
        "quiero ver antes cómo quedaría lo de Talleres Mercedes si lo corrijo",
    ),
    (
        "en",
        "invoice.invoice.rectification_preview",
        "before touching the Talleres Mercedes one, show me how the correction would look",
    ),
    ("es", "invoice.refund.get", "del reintegro de ayer a Mercedes, ¿qué número le salió?"),
    ("en", "invoice.refund.get", "Mercedes was reimbursed yesterday: which number did her rectifying one get?"),
    ("es", "invoice.issuer.get", "¿qué CIF y domicilio figuran como nuestros en lo que emitimos?"),
    ("en", "invoice.issuer.get", "whose name and tax number head our documents?"),
    ("es", "invoice.numbering.allocations", "¿a qué se le dio el 000123 en el libro?"),
    ("en", "invoice.numbering.allocations", "who got 000123, according to the ledger?"),
    ("es", "invoice.numbering.gaps", "¿nos hemos saltado alguno al numerar?"),
    ("en", "invoice.numbering.gaps", "did we skip any number somewhere along the way?"),
    ("es", "invoice.numbering.status", "¿podemos empezar a emitir en 2027 o falta preparar algo?"),
    ("en", "invoice.numbering.status", "come January, are all our numbers ready to roll?"),
    ("es", "invoice.series.list", "¿con qué prefijos y letras numeramos este año cada cosa que emitimos?"),
    ("en", "invoice.series.list", "what letters go in front of each number we hand out this year?"),
    ("es", "invoice.series.get", "quiero el detalle de la FACT de este año, sin tocar nada"),
    ("en", "invoice.series.get", "tell me the details of this year's FACT, without touching anything"),
    ("es", "invoice.series.peek_next", "sin gastarlo todavía, ¿qué número va después en la FACT?"),
    ("en", "invoice.series.peek_next", "without spending it yet, which one follows in FACT?"),
    (
        "es",
        "invoice.invoice.create",
        "a Talleres Mercedes le debemos una por la reparación de ayer: hazla a mano, 120 €",
    ),
    ("en", "invoice.invoice.create", "bill Talleres Mercedes by hand for yesterday's repair, 120 €"),
    (
        "es",
        "invoice.invoice.create_from_sale",
        "la de esta mañana, la 20261111-0007, se quedó sin documento: genéralo ya",
    ),
    ("en", "invoice.invoice.create_from_sale", "the 20261111-0007 from this morning is missing its ticket"),
    ("es", "invoice.invoice.substitute", "ese tique de ayer pásalo a nombre de Talleres Mercedes"),
    ("en", "invoice.invoice.substitute", "the man with yesterday's receipt wants it in his company's name"),
    ("es", "invoice.invoice.mark_paid", "Talleres Gómez ya nos ha abonado la FACT-2025-000412"),
    ("en", "invoice.invoice.mark_paid", "Talleres Gómez has settled FACT-2025-000412"),
    ("es", "invoice.invoice.print", "saca en papel la FACT-2025-000412"),
    ("en", "invoice.invoice.print", "FACT-2025-000412 on paper for the binder, please"),
    ("es", "invoice.invoice.rectify", "la de Talleres Mercedes tiene un error en el importe: hazle su negativo"),
    ("en", "invoice.invoice.rectify", "the Talleres Mercedes one has the wrong amount: fix it with an R1"),
    (
        "es",
        "invoice.invoice.rectify_from_refund",
        "a lo que le devolvimos a Mercedes le falta el documento que lo resta",
    ),
    (
        "en",
        "invoice.invoice.rectify_from_refund",
        "what we gave back to Mercedes this morning still has no negative document",
    ),
    ("es", "invoice.invoice.rectify_from_void", "la 20261111-0003 la anulé y aún no tiene su negativo"),
    ("en", "invoice.invoice.rectify_from_void", "after scrapping 20261111-0003 we still lack its negative"),
    ("es", "invoice.issuer.update", "ya no estamos en la calle de antes: el domicilio ahora es Avenida Castilla 8"),
    ("en", "invoice.issuer.update", "our company moved to Avenida Castilla 8: change where it is"),
    ("es", "invoice.series.create", "para la feria de 2027 quiero una numeración propia, aparte de la normal"),
    ("en", "invoice.series.create", "for the 2027 fair we want numbering of our own, apart from the usual one"),
    ("es", "invoice.series.update", "renombra la de Obras como Reformas"),
    ("en", "invoice.series.update", "please rename the Obras one: Reformas suits it better"),
]


def assert_offered_within(tools, name: str, phrase: str, within: int) -> None:
    """That ``phrase``, a person's words and none of the asks of tool ``name``, brings it among the first ``within`` a
    turn offers."""
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= within, place


def test_invoice_offers_its_twenty_five_tools():
    """Invoicing's assistant tools (``AI``, never ``INTERNAL``): a silent drop of a tool fails."""
    tools = {name for name, op in registry.items() if op.app_label == "invoice" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert tools == TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_what_rectifies_numbers_or_names_who_issues(context_of):
    for role, lacked in (
        (Membership.Role.OWNER, set()),
        (Membership.Role.ADMIN, set()),
        (Membership.Role.MANAGER, NOT_THE_MANAGERS),
        (Membership.Role.EMPLOYEE, NOT_THE_EMPLOYEES),
    ):
        offered = {name for name in assistant.catalog(context_of(role, "es")) if name.startswith("invoice.")}
        assert offered == TOOLS - lacked, role
    # Positive control: an employee marks an invoice paid and replaces a ticket (INVOICE-F05, INVOICE-F19).
    assert {"invoice.invoice.mark_paid", "invoice.invoice.substitute"} <= TOOLS - NOT_THE_EMPLOYEES


def test_the_reported_requests_are_the_probes_of_layer_2():
    assert_reported_are_owner_probes(REPORTED)
    assert {probe["tool"] for probe in PROBES} >= {name for name, _ in REPORTED}  # the probes below include them


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED, ids=[name for name, _ in REPORTED])
def test_the_reported_invoice_request_offers_its_existing_operation(context_of, name, phrase):
    assert_offered_within(assistant.catalog(context_of(Membership.Role.OWNER, "es")), name, phrase, WITH_ROOM)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), THE_ISSUES)
def test_the_request_of_the_issue_offers_its_write_near_the_top(context_of, name, phrase):
    """hub#1102: the owner asks to mark an invoice paid or to rectify it, and the write is among the first eight a turn
    offers, so the model calls it and its card comes (INVOICE-F08, INVOICE-F19)."""
    assert_offered_within(assistant.catalog(context_of(Membership.Role.OWNER, "es")), name, phrase, NEAR_THE_TOP)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_invoicing_offers_its_tool_without_being_one_of_its_asks(context_of, probe):
    """The owner's twenty-five phrases of layer 2, the ones the model answered right too: a tool of Invoicing that a
    new ask elsewhere pushes out of the first twenty fails here before the real-model QA sees it."""
    assert (probe["app"], probe["language"]) == ("invoice", "es")
    tools = assistant.catalog(context_of(ROLES[probe["role"]], "es"))
    assert_offered_within(tools, probe["tool"], probe["phrase"], WITH_ROOM)


@pytest.mark.parametrize("words", [words for words in PAID if words != "paid"])  # «paid» is its own stem already
def test_the_hub_reads_a_paid_invoice_as_paid(words):
    phrase = f"la factura de Talleres Mercedes {words}"
    paid = shared.stem("paid")
    assert any(paid in concept for concept in shared.asked(["the invoice is paid"]).concepts)  # positive control
    assert any(paid in concept for concept in shared.asked([phrase], assistant.SYNONYMS).concepts), phrase
    assert not any(paid in concept for concept in shared.asked([phrase]).concepts), phrase


@pytest.mark.parametrize("phrase", ["cobra la mesa 4 en efectivo", "¿cuánto hemos cobrado hoy?", "el cobro de ayer"])
def test_a_charge_of_the_till_is_never_read_as_a_paid_invoice(phrase):
    """«cobrar» and «cobro» alone are a sale's charge (live's group of a sale): only «como cobrada» marks one paid."""
    sale = shared.stem("sale")
    concepts = shared.asked([phrase], assistant.SYNONYMS).concepts
    assert any(sale in concept for concept in concepts)  # positive control: it names a sale
    assert not any(shared.stem("paid") in concept for concept in concepts)


def without_the_paid_group():
    """The Hub's ``SYNONYMS`` without the group of a paid invoice."""
    kept = tuple(group for group in assistant.SYNONYMS if not set(PAID) & set(group))
    assert len(kept) == len(assistant.SYNONYMS) - 1  # positive control: the group is there, and only one
    return kept


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_an_invoice_said_paid_brings_marking_it_paid_by_the_hubs_words(context_of):
    """«marca como cobrada la FACT-2026-000001»: with the Hub's words of a paid invoice, marking it paid is among the
    first eight; without them, behind the reads and writes of the sale a «cobrada» names, it is not."""
    tools = assistant.catalog(context_of(Membership.Role.OWNER, "es"))
    phrase = "marca como cobrada la FACT-2026-000001"
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert "invoice.invoice.mark_paid" in offered[:NEAR_THE_TOP], offered[:NEAR_THE_TOP]
    ranking = {**assistant.RANKING, "synonyms": without_the_paid_group()}
    unnamed = [op.name for op in shared.relevant(tools, [phrase], "es", **ranking)]
    assert "invoice.invoice.mark_paid" not in unnamed[:NEAR_THE_TOP], unnamed[:NEAR_THE_TOP]


def test_each_tool_of_invoicing_has_its_own_words_in_each_language():
    """One phrase per tool and language: only the asks of the language a phrase is said in bring it, so a tool with
    words of its own in one language only leaves its asks in the other unmeasured (hub#1216)."""
    assert sorted((name, language) for language, name, _ in OWN_WORDS) == sorted(
        (name, language) for name in TOOLS for language in ("en", "es")
    )


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    ("language", "name", "phrase"), OWN_WORDS, ids=[f"{name}-{language}" for language, name, _ in OWN_WORDS]
)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(context_of, language, name, phrase):
    assert_its_asks_bring(assistant.catalog(context_of(Membership.Role.OWNER, language)), name, phrase, language)
