"""What layer 1 of the assistant's QA does not say of the WhatsApp inbox (docs plan 2026-10-31, the assistant's knowledge
and QA, §3): how many tools it offers, and that the owner's requests of the real-model QA (hub#1108), in the owner's
own words, are offered their existing operation.

Every ask of every tool of whatsapp_inbox bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (whatsapp_inbox is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as
``live.E020`` over the asks and the guard that no ask copies a probe of layer 2.
"""

import json

import pytest
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tests.test_assistant_asks import PROBES, TOP, comparable, probe_phrases

A = Scope("host", "a")

#: The requests of hub#1108's QA (``owner.es.whatsapp_inbox.*`` of ``owner-es-whatsapp_inbox-2026-11-08.json``), as the
#: owner said them: before the inbox said its asks, none of these tools was among the ones a turn offers
#: (``MAX_TOOLS``), so the model answered it had no tool to read the inbox (``message.get``) or picked another one.
#: Each is offered its existing operation now, without being one of its asks.
REPORTED = [
    (
        "whatsapp_inbox.message.get",
        "abre el último mensaje de Web QA con su texto, número, fecha y opciones que le ofrecimos",
    ),
    ("whatsapp_inbox.agent.list", "¿a qué personas del equipo puedo asignar una conversación de WhatsApp?"),
    ("whatsapp_inbox.message.retry", "reintenta el último mensaje que no salió con la misma clave, sin duplicarlo"),
    (
        "whatsapp_inbox.message.send",
        "responde por WhatsApp al +34 611 999 888: «Recibido, te confirmo la cita en un momento»",
    ),
    ("whatsapp_inbox.template.retry", "reintenta registrar la plantilla Recordatorio QA sin crearla dos veces"),
    (
        "whatsapp_inbox.template.update",
        "cambia Recordatorio QA para que diga «Tu cita queda para {{1}}» y vuelve a enviarla a revisión",
    ),
]
#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a request of the QA may bring its tool: half of them, so
#: twenty tools of the apps that say their asks later may climb past it before the model loses it (measured on this
#: branch: the 17th at worst, ``message.send`` and ``template.update``; on main, without the inbox's asks, six were
#: not offered at all and six more came between the 20th and the 33rd).
WITH_ROOM = 20
#: What the inbox's groups of ``base.assistant.SYNONYMS`` are for, in a turn: a request nobody wrote as an ask nor as
#: a probe, the tool it brings among the first ten (``TOP``) and the word of its group. Without the group, the other
#: writes of the Hub tie with ``template.create`` and win by name (the 11th), and ``message.list`` is the 15th.
BY_GROUP = [
    ("whatsapp_inbox.template.create", "haz otra plantilla para avisar de las rebajas", "plantilla"),
    ("whatsapp_inbox.message.list", "¿cuántos mensajes tiene la conversación de Rocío?", "mensaje"),
]


def whatsapp_probes() -> list[tuple[str, str, str]]:
    """Every probe of layer 2 of a WhatsApp inbox tool (``tests/e2e/qa/probes/*-es-whatsapp_inbox-*.json``): its role,
    tool and phrase, as the QA wrote it and nobody wrote it as an ask."""
    return [
        (Membership.Role[probe["role"].upper()], probe["tool"], probe["phrase"])
        for path in sorted(PROBES.glob("*-es-whatsapp_inbox-*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    ]


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(
            scope=A, actor=user.username, permissions=permissions_for(user, A), language=language
        )
        return assistant.catalog(ctx)

    return of


def test_the_inbox_offers_at_least_30_tools():
    """The inbox's tools are at least 30 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {
        name for name, op in registry.items() if op.app_label == "whatsapp_inbox" and isinstance(op.ai_spec(), AI)
    }
    assert len(tools) >= 30


def test_the_hub_reads_plantilla_and_mensaje_as_the_inboxs_template_and_message():
    """``base.assistant.SYNONYMS``: a «plantilla» and a «mensaje» are what an English «template» and «message» are, the
    inbox's (``whatsapp_inbox.template``, ``whatsapp_inbox.message``, the only ones a tool of the Hub acts on); without
    the Hub's groups, Spanish names neither (positive control)."""
    template, message = shared.stem("template"), shared.stem("message")
    for phrase, wanted in (
        ("borra la plantilla de bienvenida", template),
        ("¿qué plantillas tengo aprobadas?", template),
        ("reenvía el mensaje de Nuria", message),
        ("¿han leído nuestros mensajes?", message),
    ):
        assert any(wanted in concept for concept in shared.asked([phrase], assistant.SYNONYMS).concepts), phrase
        assert not any(wanted in concept for concept in shared.asked([phrase]).concepts), phrase


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase", "word"), BY_GROUP)
def test_a_request_in_spanish_brings_its_tool_among_the_first_ten_by_the_inboxs_groups(catalog_of, name, phrase, word):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert name in tools  # positive control: the owner holds it, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    assert comparable(phrase) not in probe_phrases()
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered[:TOP], (offered.index(name) + 1 if name in offered else None, offered[:TOP])
    without = tuple(group for group in assistant.SYNONYMS if word not in group)
    unread = [op.name for op in shared.relevant(tools, [phrase], "es", **{**assistant.RANKING, "synonyms": without})]
    assert name not in unread[:TOP]  # positive control: the group is what brings it


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [f"owner.es.{name}" for name, _ in REPORTED]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_whatsapp_request_offers_its_existing_operation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:TOP])


def test_layer_2_probes_every_whatsapp_tool():
    """The sweep below is whole: there is a probe of layer 2 for every tool of the inbox, read from its files."""
    probed = {tool for _, tool, _ in whatsapp_probes()}
    tools = {name for name, op in registry.items() if op.app_label == "whatsapp_inbox" and assistant.is_tool(op)}
    assert probed == tools, sorted(probed ^ tools)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize(("role", "name", "phrase"), whatsapp_probes())
def test_every_whatsapp_probe_of_layer_2_is_offered_its_tool_without_being_its_asks(catalog_of, role, name, phrase):
    """Not only the six the QA found unreachable: each request of the QA of the inbox, in the words it was said in and
    by the role that said it, is among the first ``WITH_ROOM`` tools a turn offers, so the model can choose it and an
    app that says its asks later cannot push it out unseen."""
    tools = catalog_of(role, "es")
    assert name in tools  # positive control: the role holds it, so the model can receive it
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:TOP])
