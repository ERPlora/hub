"""What layer 1 of the assistant's QA does not say of the WhatsApp inbox: how many tools it offers, and that the owner's
requests of the real-model QA (hub#1108), in the owner's own words, are offered their existing operation.

Every ask of every tool of whatsapp_inbox bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (whatsapp_inbox is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as
``live.E020`` over the asks and the guard that no ask copies a probe of layer 2.
"""

import json

import pytest
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import PROBES, TOP, assert_its_asks_bring, assert_offered_with_room
from base.tests.test_assistant_asks import assert_reported_are_owner_probes, comparable, offered_place, offered_to
from base.tests.test_assistant_asks import probe_phrases
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

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
#: What the inbox's groups of ``base.assistant.SYNONYMS`` are for, in a turn: a request nobody wrote as an ask nor as
#: a probe, the tool it brings among the first ten (``TOP``) and the word of its group. Without the group, the other
#: writes of the Hub tie with ``template.create`` and win by name (the 11th), and ``message.list`` is the 15th.
BY_GROUP = [
    ("whatsapp_inbox.template.create", "haz otra plantilla para avisar de las rebajas", "plantilla"),
    ("whatsapp_inbox.message.list", "¿cuántos mensajes tiene la conversación de Rocío?", "mensaje"),
]
#: What a person says in words of their own, neither an ask nor a probe of layer 2, one per tool of the inbox: their
#: asks bring each among the first ten (``TOP``), and without them it is not (the probes reach several of these tools by
#: their name, their description and the groups alone), so asks that stop reading as people speak fail here. They keep
#: away from the words of the apps that say their asks after the inbox: «número» (Payments) and «opciones» (Menus'
#: group) took ``channel.prepare`` and ``message.get`` past the tenth.
OWN_WORDS = [
    ("whatsapp_inbox.agent.list", "¿quién atiende hoy los WhatsApp?"),
    ("whatsapp_inbox.channel.get", "¿cuánto cupo nos queda este mes?"),
    ("whatsapp_inbox.channel.connect", "toma el código que me ha dado Meta y termina la conexión"),
    ("whatsapp_inbox.channel.disconnect", "desconéctanos de WhatsApp unos días"),
    ("whatsapp_inbox.channel.prepare", "¿qué hace falta para la conexión con Meta?"),
    ("whatsapp_inbox.conversation.assign", "que se quede Elena con el chat de Raúl"),
    ("whatsapp_inbox.conversation.by_phone", "¿nos ha escrito alguna vez el +34 655 444 333?"),
    ("whatsapp_inbox.conversation.count_awaiting_reply", "¿a cuántos les debemos respuesta?"),
    ("whatsapp_inbox.conversation.detail", "¿quién lleva el chat de Raúl?"),
    ("whatsapp_inbox.conversation.erase", "borra todos sus datos a Raúl, lo ha pedido por protección de datos"),
    ("whatsapp_inbox.conversation.flag", "el bot no entendió a Raúl, que lo atienda alguien"),
    ("whatsapp_inbox.conversation.link_customer", "junta el chat de Raúl con su ficha"),
    ("whatsapp_inbox.conversation.list", "¿qué chats están cerrados?"),
    ("whatsapp_inbox.conversation.mark_read", "lo de Raúl dalo por leído"),
    ("whatsapp_inbox.conversation.notices", "¿alguien nos ha escrito esta mañana?"),
    ("whatsapp_inbox.conversation.set_status", "cambia el estado del chat de Raúl a pendiente"),
    ("whatsapp_inbox.conversation.summary", "hazme un resumen de WhatsApp"),
    ("whatsapp_inbox.message.get", "¿qué decía lo que mandó Raúl esta mañana?"),
    ("whatsapp_inbox.message.list", "enséñame el hilo de Raúl"),
    ("whatsapp_inbox.message.notify", "manda un aviso a Raúl de que su cita queda movida"),
    ("whatsapp_inbox.message.retry", "vuelve a mandar el que falló"),
    ("whatsapp_inbox.message.send", "escríbele a Raúl que mañana cerramos"),
    ("whatsapp_inbox.note.add", "apunta en el chat de Raúl que es alérgico al marisco"),
    ("whatsapp_inbox.note.delete", "quita lo que apunté sobre Raúl en su chat"),
    ("whatsapp_inbox.note.list", "¿alguien dejó algo apuntado en el chat de Raúl?"),
    ("whatsapp_inbox.template.create", "necesito una plantilla para dar las gracias tras la visita"),
    ("whatsapp_inbox.template.delete", "borra la de la promoción vieja"),
    ("whatsapp_inbox.template.list", "¿me han aprobado ya la de bienvenida?"),
    ("whatsapp_inbox.template.retry", "a Meta no le ha llegado la de cumpleaños, reinténtalo"),
    ("whatsapp_inbox.template.update", "cambia el pie de la de bienvenida"),
    ("whatsapp_inbox.template_sample.detail", "¿qué archivo subí de cabecera?"),
    ("whatsapp_inbox.template_sample.upload", "usa este PDF como cabecera"),
]
#: The tools of other apps whose asks say their own words because the «plantilla» group took their place (each fell to
#: the 13th or the 16th): «plantilla de negocio», «business templates» and «el personal».
REWRITTEN = ("base.blueprint.list", "staff.member.bulk_create")
#: The places an ask of another app keeps free below the first ten: the asks of the next app to say its own take them.
ROOM = 2
#: Who loads a business template and the whole staff (``base.administer_hub``, ``staff.add_member``): the roles both hold.
RUN_THE_BUSINESS = (Membership.Role.OWNER, Membership.Role.ADMIN)


def whatsapp_probes() -> list[tuple[str, str, str]]:
    """Every probe of layer 2 of a WhatsApp inbox tool (``tests/e2e/qa/probes/*-es-whatsapp_inbox-*.json``): its role,
    tool and phrase, as the QA wrote it and nobody wrote it as an ask."""
    return [
        (Membership.Role[probe["role"].upper()], probe["tool"], probe["phrase"])
        for path in sorted(PROBES.glob("*-es-whatsapp_inbox-*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    ]


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
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(tools, name, phrase, room=TOP)
    without = tuple(group for group in assistant.SYNONYMS if word not in group)
    # positive control: the group is what brings it
    assert name not in offered_to(tools, phrase, synonyms=without)[:TOP]



def test_the_reported_requests_are_the_probes_of_layer_2():
    assert_reported_are_owner_probes(REPORTED)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_whatsapp_request_offers_its_existing_operation(catalog_of, name, phrase):
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, "es"), name, phrase)


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
    assert_offered_with_room(catalog_of(role, "es"), name, phrase)


def test_every_tool_of_the_inbox_has_its_own_words():
    """``OWN_WORDS`` is whole: one phrase for every tool of the inbox, so neutralising the asks of any of them fails."""
    tools = {name for name, op in registry.items() if op.app_label == "whatsapp_inbox" and assistant.is_tool(op)}
    named = [name for name, _ in OWN_WORDS]
    assert sorted(named) == sorted(tools), sorted(set(named) ^ tools)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_the_owners_own_words_reach_each_tool_of_the_inbox_by_its_asks(catalog_of, name, phrase):
    assert_its_asks_bring(catalog_of(Membership.Role.OWNER, "es"), name, phrase, "es")


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", RUN_THE_BUSINESS)
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("name", REWRITTEN)
def test_the_inboxs_templates_take_no_place_from_the_business_templates_nor_the_staff(catalog_of, name, language, role):
    """A business template (``base.blueprint.list``) and loading the whole staff (``staff.member.bulk_create``) are no
    template of the inbox: said with «plantilla» or «templates» alone, their asks fell to the 13th and the 16th with the
    «plantilla» group; said with their own words, each keeps ``ROOM`` places below the last one
    ``base/tests/test_assistant_asks.py`` allows."""
    tools = catalog_of(role, language)
    asks = shared.asks_of(tools[name])[language]
    places = {ask: offered_place(tools, name, ask, language) for ask in asks}
    assert {ask: place for ask, place in places.items() if place is None or place > TOP - ROOM} == {}
