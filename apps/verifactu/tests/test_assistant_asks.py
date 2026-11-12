"""What layer 1 of the assistant's QA says of VeriFactu: its thirty-one tools, what an employee is never offered, and
that the requests of the real-model QA, in the owner's and the employee's own words, are offered their existing
operation on the record already there.

Every ask of every tool of verifactu bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(verifactu is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks and the guards that no ask
copies a probe of layer 2 and no test here ranks an ask as a person's words.

Nothing here runs an operation: a turn's ranking reads the catalogue and the phrases only, so no test files a record
with the AEAT, of testing or of production; a connection to anything but this machine fails the test (``no_way_out``).
"""

import ipaddress
import json
import socket
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
# ``context_of`` is base's fixture (a member of business ``a``, which has every app on, with a role and a language):
# imported here, pytest hands it to the tests of this module as it does to base's.
from base.tests.test_assistant_asks import (
    assert_its_asks_bring,
    comparable,
    context_of,
    place_of_no_ask,
    probe_phrases,
)

#: The requests of the real-model QA (``tests/e2e/qa/probes/owner-es-verifactu-2026-11-08.json``), as the owner said
#: them, and nothing of the tools' ``asks``: before VeriFactu said its asks, none of these tools was among the ones a
#: turn offers (``MAX_TOOLS``) but the queue's retry (24th), so the model answered it had no tool, sent the owner to the
#: Recovery screen or created another test invoice instead of sealing the record of the one already issued. The last one
#: the model answered right, but Taxes' asks («fiscal», «registro») took it out of the ones a turn offers.
REPORTED = [
    ("verifactu.stats.events_recent", "¿cuáles son los cinco acontecimientos fiscales más recientes?"),
    (
        "verifactu.chain.validate",
        "recalcula las huellas de toda la cadena del emisor en pruebas y comprueba que cada eslabón enlaza con el "
        "anterior",
    ),
    (
        "verifactu.contingency.retry",
        "adelanta el registro de la factura de prueba para que salga con sus anteriores en el próximo pase, sin borrar "
        "sus intentos",
    ),
    (
        "verifactu.record.create",
        "sella y encadena el registro de la factura de prueba si aún no existiera, con su QR y su lugar en la cola",
    ),
    (
        "verifactu.diagnostic.last",
        "¿qué resultado dio la última comprobación de conexión con la vía de envío fiscal?",
    ),
]
#: What the owner says in short of the two writes of the issue, beside the QA's long phrases: validating the chain and
#: putting the record of the queue out sooner.
SAID_SHORT = [
    ("verifactu.chain.validate", "valida la cadena"),
    ("verifactu.contingency.retry", "adelanta el registro de la cola"),
]
#: How far down the tools a turn offers the requests of the issue bring their tool: the model weighs the first ones.
FIRST = 8
#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a probe of the QA may bring its tool: half of them, so the
#: tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
PROBES_DIR = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"
#: Every probe of layer 2 of VeriFactu, the owner's and the employee's real phrases of the QA: the ones above and the
#: ones the model answered right.
PROBES = [
    probe
    for path in sorted(PROBES_DIR.glob("*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    if probe["app"] == "verifactu"
]
#: The probe of going live: «la cuenta» (ERPlora's account) is read as a table's check, so every write of Sales that
#: takes a check and «activa» turns on goes ahead of it; it is offered, past the first half.
GO_LIVE = "qa20261108.owner.es.verifactu.config.go_live"
#: Why that probe is marked: whoever brings the pointer of live with ERPlora/live#76 sees it pass and takes it off.
UNTIL_LIVE_TELLS_THE_ACCOUNT_FROM_A_CHECK = pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="ERPlora/live#76: «la cuenta» of ERPlora is read as a table's check"
)
#: What a person says in words of their own, neither an ask nor a probe of layer 2, one per tool of VeriFactu: each
#: reaches its tool among the first ten by its asks and not without them, so asks that stop reading as people speak fail
#: here, tool by tool. None says more than two content words of any one of its asks or of its probes, nor half of its
#: own; none names the thing of its tool as the Hub reads it («contingencia», «diagnóstico»,
#: «certificado», «modelo», «procesa»: they bring it by its name alone), nor «presenta» (the stem of attendance's
#: presence), which live reads as another thing. Live reads «sella», «producción» and «comprueba» as what they are,
#: not as a sale, a product and a purchase.
OWN_WORDS = [
    (
        "verifactu.config.get",
        "la asesora pregunta por qué vía mandamos a la Agencia Tributaria y si seguimos en pruebas",
    ),
    ("verifactu.record.list", "para la asesoría, saca los registros de septiembre que siguen sin subsanar"),
    ("verifactu.record.get", "la asesora quiere la huella y lo que respondió la Agencia Tributaria al 31"),
    ("verifactu.record.by_invoice", "necesito el QR de la factura F-2026-0031 para reimprimirla"),
    ("verifactu.contingency.list", "la asesora quiere saber qué registros tenemos todavía camino de Hacienda"),
    ("verifactu.event.list", "la asesoría quiere ver las incidencias graves de la auditoría del lunes"),
    ("verifactu.stats.compliance_summary", "la asesora pregunta si nos queda algo por llegar a la Agencia Tributaria"),
    ("verifactu.stats.records_by_status", "la asesoría quiere el reparto de lo aceptado y lo rechazado"),
    ("verifactu.stats.contingency_summary", "¿están fallando los envíos a Hacienda o van bien?"),
    ("verifactu.stats.events_recent", "¿qué sucesos recientes ha habido con la Agencia Tributaria?"),
    ("verifactu.aeat_record.list", "la asesora quiere saber qué dice la Agencia Tributaria que le consta"),
    ("verifactu.chain.status", "la asesoría quiere la huella actual de la cadena"),
    ("verifactu.diagnostic.last", "¿pasamos la última prueba de conexión con la Agencia Tributaria?"),
    ("verifactu.representation.model", "prepárame el apoderamiento relleno con nuestros datos para Begoña"),
    ("verifactu.record.create", "a la F-2026-0031 que emitió Begoña le falta encadenarse"),
    ("verifactu.record.correct", "la asesora pide subsanar el 31, que vino rechazado"),
    (
        "verifactu.record.cancel",
        "la factura de Amaia fue una equivocación y la emitimos igualmente, que no conste en ningún sitio",
    ),
    ("verifactu.record.transmit", "remite el 31 a la Agencia Tributaria con los anteriores de su cadena"),
    ("verifactu.contingency.process", "Begoña y la asesora quieren que despachemos todo lo que toque"),
    ("verifactu.contingency.retry", "adelanta el 31 a la próxima pasada, que lo necesita la asesora"),
    ("verifactu.record.reconcile", "el 31 se quedó sin respuesta: concílialo con la Agencia Tributaria"),
    ("verifactu.chain.validate", "la asesora quiere que recalcules la cadena por si está rota"),
    ("verifactu.chain.recover_manual", "venimos de otro software: empalma con su última huella"),
    ("verifactu.aeat.query", "la asesora quiere la relación de lo que tiene Hacienda de septiembre"),
    (
        "verifactu.chain.recover_from_aeat",
        "la asesora dice que tras volver a la copia de seguridad hay que rehacer lo de Hacienda",
    ),
    ("verifactu.diagnostic.run", "¿llegamos bien a la Agencia Tributaria? pruébalo sin remitir nada"),
    ("verifactu.test_invoice.create", "Begoña quiere ver si funciona todo con la prueba de un euro"),
    ("verifactu.config.update", "a partir de ahora que lo remita ERPlora, la asesora está de acuerdo"),
    ("verifactu.config.go_live", "la asesora dice que ya podemos remitir de verdad a Hacienda"),
    ("verifactu.config.back_to_testing", "vuelve VeriFactu a pruebas hasta que la asesoría dé el visto bueno"),
    ("verifactu.certificate.remove", "la asesora dice que ya no usamos la firma digital que subimos: elimínala"),
]
#: What takes a secret, a document or the platform's word, never a tool of the chat: the own certificate and the signed
#: authorisation go on the screen, the account's photo and the deployment's environment are the system's.
NOT_TOOLS = {
    "verifactu.certificate.upload",
    "verifactu.representation.submit",
    "verifactu.config.sync",
    "verifactu.config.follow_deployment",
}


@pytest.fixture(autouse=True)
def no_way_out(monkeypatch):
    """No test here leaves this machine: a connection to anything else (the AEAT, of testing or of production, or
    ERPlora's gateway) fails it, so ranking a fiscal request is never a filing."""
    connect = socket.socket.connect

    def here(host: str) -> bool:
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:  # a name: only this machine's
            return host == "localhost"

    def only_here(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not here(address[0]):
            raise AssertionError(f"a test of VeriFactu's asks opened a connection to {address}")
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", only_here)


def owners_catalog(context_of, language: str = "es") -> dict[str, Operation]:
    """The real catalogue of the assistant of the owner of business ``a``, which has every app on."""
    return assistant.catalog(context_of(Membership.Role.OWNER, language))


def verifactu_tools() -> list[str]:
    return sorted(name for name, op in registry.items() if op.app_label == "verifactu" and assistant.is_tool(op))


def test_nothing_here_reaches_the_aeat():
    """Positive control of ``no_way_out``: a connection to an address off this machine fails before it is made."""
    with pytest.raises(AssertionError, match="opened a connection"):
        socket.create_connection(("192.0.2.1", 443), timeout=1)


def test_verifactu_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """VeriFactu is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its asks
    for every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "verifactu" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_verifactu_offers_its_thirty_one_tools():
    """VeriFactu's tools are its thirty-one operations (``AI``, never ``INTERNAL``): a silent drop of a tool fails. What
    takes a secret or is the system's is none."""
    tools = verifactu_tools()
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) == 31
    assert {name for name, _ in REPORTED} <= set(tools)
    assert NOT_TOOLS <= set(registry)  # positive control: they are operations, only not tools
    assert NOT_TOOLS.isdisjoint(tools)


def test_the_reported_requests_are_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"qa20261108.owner.es.{name}" for name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED + SAID_SHORT)
def test_the_owners_request_offers_its_existing_operation_among_the_first_eight(context_of, name, phrase):
    place = place_of_no_ask(owners_catalog(context_of), name, phrase)
    assert place is not None and place <= FIRST, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_sealing_the_record_of_an_issued_invoice_comes_before_creating_another_test_invoice(context_of):
    """The owner asked to seal the record of the test invoice already issued, and the model created another
    test invoice (``verifactu.test_invoice.create``): sealing the record of an issued invoice goes ahead of it."""
    tools = owners_catalog(context_of)
    ranked = [op.name for op in assistant.relevant(tools, [dict(REPORTED)["verifactu.record.create"]], "es")]
    assert "verifactu.record.create" in ranked
    assert "verifactu.test_invoice.create" in tools  # positive control: the owner may create one
    later = ranked.index("verifactu.test_invoice.create") if "verifactu.test_invoice.create" in ranked else len(ranked)
    assert ranked.index("verifactu.record.create") < later


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize(
    "probe",
    [
        pytest.param(probe, marks=UNTIL_LIVE_TELLS_THE_ACCOUNT_FROM_A_CHECK) if probe["id"] == GO_LIVE else probe
        for probe in PROBES
    ],
    ids=[probe["id"] for probe in PROBES],
)
def test_every_probe_of_verifactu_offers_its_tool_to_whoever_may_run_it(context_of, probe):
    """The phrases of layer 2 of VeriFactu, the ones the model answered right too: a tool of VeriFactu that a new ask
    elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees it. What
    the employee asks of a write only who runs the business holds is a refusal: the tool is not theirs to be offered."""
    assert probe["language"] == "es"  # the QA of VeriFactu asked in Spanish: base's place_of_no_ask ranks in it
    role = {"owner": Membership.Role.OWNER, "employee": Membership.Role.EMPLOYEE}[probe["role"]]
    tools = assistant.catalog(context_of(role, probe["language"]))
    if probe["expect"] == "refused":
        assert probe["role"] == "employee"
        assert probe["tool"] in owners_catalog(context_of, probe["language"])
        assert probe["tool"] not in tools
        return
    place = place_of_no_ask(tools, probe["tool"], probe["phrase"])
    assert place is not None and place <= WITH_ROOM, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_going_live_is_offered_although_the_account_is_read_as_a_check(context_of):
    """Before VeriFactu said its asks, going live was not offered at all for the owner's request; now it is, behind the
    writes of a check that «activa … la cuenta» brings (``GO_LIVE``)."""
    probe = next(probe for probe in PROBES if probe["id"] == GO_LIVE)
    place = place_of_no_ask(owners_catalog(context_of), probe["tool"], probe["phrase"])
    assert place is not None and place <= shared.MAX_TOOLS, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(context_of, name, phrase):
    assert_its_asks_bring(owners_catalog(context_of), name, phrase, "es")


def test_every_tool_of_verifactu_has_a_phrase_of_its_own():
    """``OWN_WORDS`` covers every tool once: a tool whose asks no phrase of a person's own reaches would let its asks
    change unseen (the sweep of ``base`` ranks only the asks themselves)."""
    assert sorted(name for name, _ in OWN_WORDS) == verifactu_tools()
