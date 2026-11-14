"""What layer 1 of the assistant's QA does not say of Staff: how many tools it offers, and that the owner's requests of
the real-model QA, in the owner's own words, are offered their existing operation.

Every ask of every tool of staff bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (staff is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over
the asks and the guard that no ask copies a probe of layer 2.
"""

import json

import pytest
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import PROBES, TOP, assert_offered_with_room, comparable, place_of_no_ask
from base.tests.test_assistant_asks import probe_phrases
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

#: The requests of the real-model QA (``owner.es.staff.*`` of ``owner-es-staff-2026-11-08.json``), as the owner said
#: them: before Staff said its asks, none of these tools was among the ones a turn offers (``MAX_TOOLS``), so the model
#: read a list without the reason, picked ``customer.customer.delete``, asked what kind of record it was, or said it
#: could not. Each is offered its existing operation now, without being one of its asks.
REPORTED = [
    (
        "staff.time_off.detail",
        "abre la ausencia de Personal QA del 20 de noviembre con motivo, notas y quién la aprobó",
    ),
    ("staff.member.deactivate", "desactiva a Ayudante Uno QA sin borrar su ficha ni su historial"),
    ("staff.role.update", "renombra Coordinación QA como «Coordinación diaria QA» y ponlo el primero"),
    (
        "staff.time_off.reject",
        "rechaza la ausencia pendiente de Personal QA del 21 de noviembre y deja constancia de la decisión",
    ),
]


def staff_probes() -> list[tuple[str, str, str]]:
    """Every probe of layer 2 of a Staff tool (``tests/e2e/qa/probes/*-es-staff-*.json``): its role, tool and phrase,
    as the QA wrote it and nobody wrote it as an ask."""
    return [
        (Membership.Role[probe["role"].upper()], probe["tool"], probe["phrase"])
        for path in sorted(PROBES.glob("*-es-staff-*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    ]


def test_staff_offers_at_least_30_tools():
    """Staff's tools are at least 30 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "staff" and isinstance(op.ai_spec(), AI)}
    assert len(tools) >= 30


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"owner.es.{name}" for name, _ in REPORTED
    ]


def test_the_hub_reads_desactivar_as_a_deactivation_and_pido_as_a_request():
    """``base.assistant.SYNONYMS``: «desactiva» names what ``staff.member.deactivate`` does and «pido» or «una solicitud»
    what ``staff.time_off.request`` records, so the owner's words reach those tools, whose actions no verb of the
    assistant reads; without the Hub's groups, none of them does (positive control)."""
    deactivate, request = shared.stem("deactivate"), shared.stem("request")
    for phrase, wanted in (
        ("desactiva a Pablo", deactivate),
        ("pido el viernes libre", request),
        ("mira mi solicitud de vacaciones", request),
    ):
        concepts = shared.asked([phrase], assistant.SYNONYMS).concepts
        assert any(wanted in concept for concept in concepts), phrase
        assert not any(wanted in concept for concept in shared.asked([phrase]).concepts), phrase


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.EMPLOYEE])
def test_what_one_asks_for_oneself_brings_the_request_among_the_first_ten(catalog_of, role):
    """What the «pido» group of ``base.assistant.SYNONYMS`` is for, in a turn: a request for oneself nobody wrote as
    an ask nor as a probe brings ``staff.time_off.request`` among the first ten (``TOP``), before the weeks of the rota
    and the approvals; without the group, «pido vacaciones…» leaves it the 36th of the owner's 40 and the 16th of an
    employee's."""
    name, phrase = "staff.time_off.request", "pido vacaciones la primera semana de julio"
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(catalog_of(role, "es"), name, phrase, room=TOP)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_staff_request_offers_its_existing_operation(catalog_of, name, phrase):
    assert place_of_no_ask(catalog_of(Membership.Role.OWNER, "es"), name, phrase) is not None


def test_layer_2_probes_every_staff_tool():
    """The sweep below is whole: there is a probe of layer 2 for every Staff tool, read from its files."""
    probed = {tool for _, tool, _ in staff_probes()}
    tools = {name for name, op in registry.items() if op.app_label == "staff" and assistant.is_tool(op)}
    assert probed == tools, sorted(probed ^ tools)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize(("role", "name", "phrase"), staff_probes())
def test_every_staff_probe_of_layer_2_is_offered_its_tool_without_being_its_asks(catalog_of, role, name, phrase):
    """Not only the four the QA found unreachable: each request of the QA of Staff, in the words it was said in and by
    the role that said it, is among the tools a turn offers, so the model can choose it."""
    assert place_of_no_ask(catalog_of(role, "es"), name, phrase) is not None
