"""The signed calls of the Hub's assistant to erplora.com's gateway (``base/assistant/gateway.py``:
``/internal/assistant/*``, ``/internal/speech/transcribe``) and the turn it streams back.

The gateway is ``fake_gateway.FakeGateway``: a real HTTP server on 127.0.0.1 that answers in the gateway's contract.
"""

import asyncio

import pytest

from base import assistant
from base.tenancy.tests.business import A
from base.tests.fake_gateway import gateway, signed

__all__ = ["gateway", "signed"]


# ── The gateway's doors, signed ──────────────────────────────────────────────────────────────────────────────────


def test_the_allowance_is_asked_signed_and_for_this_business(gateway):
    gateway.reply("/internal/assistant/usage", json={"used": 8, "limit": 10, "resets_at": "2026-11-01T00:00:00Z", "demo": False})
    assert assistant.gateway.usage(A) == {"used": 8, "limit": 10, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
    seen = gateway.sent("/internal/assistant/usage")[0]
    assert seen.body == {"hub": A.key}
    assert signed(seen)


def test_a_gateway_that_does_not_answer_is_said_never_made_up(settings):
    settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
    with pytest.raises(assistant.gateway.GatewayError) as caught:
        assistant.gateway.usage(A)
    assert caught.value.code == "assistant.unreachable"


def test_a_report_goes_to_erplora_with_the_question_and_the_answer(gateway):
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    answer = assistant.gateway.report(A, message_id="m1", reason="incorrect", comment="", question="¿Qué vendí?", answer="Nada")
    assert answer == {"sent": True, "duplicate": False}
    seen = gateway.sent("/internal/assistant/report")[0]
    assert seen.body == {"hub": A.key, "message_id": "m1", "reason": "incorrect", "comment": "", "question": "¿Qué vendí?", "answer": "Nada"}
    assert signed(seen)


def test_a_report_that_could_not_be_sent_says_so(gateway):
    gateway.reply("/internal/assistant/report", status=503, json={"error": {"code": "assistant.report_not_sent", "message": "x"}})
    with pytest.raises(assistant.gateway.GatewayError) as caught:
        assistant.gateway.report(A, message_id="m1", reason="other", comment="", question="", answer="x")
    assert caught.value.code == "assistant.report_not_sent"


def test_a_dictation_is_transcribed_by_erplora(gateway):
    gateway.reply("/internal/speech/transcribe", json={"text": "cobra la mesa 4", "language": "es"})
    assert assistant.gateway.transcribe(A, audio="UklGRg==", mime_type="audio/webm", language="es") == {"text": "cobra la mesa 4", "language": "es"}
    assert gateway.sent("/internal/speech/transcribe")[0].body == {"hub": A.key, "audio": "UklGRg==", "mime_type": "audio/webm", "language": "es"}


# ── The turn, streamed ───────────────────────────────────────────────────────────────────────────────────────────


def frames_of(**kwargs):
    async def collect():
        return [frame async for frame in assistant.gateway.stream_turn(A, **kwargs)]

    return asyncio.run(collect())


TURN = {"messages": [{"role": "user", "content": "hola"}], "tools": [], "instructions": "x", "continuation": None}


def test_the_answer_arrives_piece_by_piece_and_closes_with_what_to_keep(gateway):
    gateway.turn(
        {"type": "text_delta", "text": "Hola"},
        {"type": "text_delta", "text": ", Ana"},
        {"type": "response", "output": [], "usage": {}, "continuation": None},
        {"type": "usage", "used": 3, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False},
    )
    frames = frames_of(**TURN)
    assert [frame["type"] for frame in frames] == ["text", "text", "usage", "done"]
    assert "".join(frame["text"] for frame in frames if frame["type"] == "text") == "Hola, Ana"
    assert frames[-1]["append"] == [{"role": "assistant", "content": "Hola, Ana"}]
    assert frames[-1]["pending"] == []
    sent = gateway.sent("/internal/assistant/chat/stream")[0]
    assert sent.body["hub"] == A.key and sent.body["messages"] == TURN["messages"]
    assert signed(sent)


def test_the_tools_the_model_asks_for_wait_with_their_continuation(gateway):
    call = {"type": "function_call", "name": "demo__item__list", "call_id": "c1", "arguments": "{}"}
    gateway.turn(call, {"type": "response", "output": [call], "usage": {}, "continuation": "tok"})
    done = frames_of(**TURN)[-1]
    assert done["pending"] == [{"call_id": "c1", "name": "demo__item__list", "arguments": "{}"}]
    assert done["continuation"] == "tok"
    assert done["append"] == [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "demo__item__list", "arguments": "{}"}}
        ]}
    ]


def test_an_allowance_spent_is_not_a_breakdown(gateway):
    gateway.reply(
        "/internal/assistant/chat/stream",
        status=429,
        json={"error": {"code": "assistant.quota_exceeded", "message": "x", "upgrade_required": True, "used": 30,
                        "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}},
    )
    error = frames_of(**TURN)[-1]
    assert error["type"] == "error"
    assert (error["code"], error["used"], error["limit"]) == ("assistant.quota_exceeded", 30, 30)


@pytest.mark.parametrize(
    "status, code, expected",
    [
        (503, "assistant.no_model", "assistant.unavailable"),
        (503, "assistant.provider_not_configured", "assistant.unavailable"),
        (403, "hub_inactive", "assistant.unavailable"),
        (413, "payload_too_large", "assistant.too_large"),
        (429, "rate_limited", "assistant.rate_limited"),
    ],
)
def test_a_refusal_of_the_gateway_is_one_of_ours(gateway, status, code, expected):
    """Each refusal is said as it is, never as a generic «Could not reach the assistant»."""
    gateway.reply("/internal/assistant/chat/stream", status=status, json={"error": {"code": code, "message": "x"}}, headers={"Retry-After": "40"})
    error = frames_of(**TURN)[-1]
    assert (error["type"], error["code"]) == ("error", expected)


#: A turn that brought pages of the web says so before the text that uses them (hub#870): what was said before a failure
#: may quote them, so the mark stays.
SEARCHED = pytest.mark.parametrize("searched", [False, True], ids=["no-web", "web"])


@SEARCHED
def test_a_provider_that_fails_half_way_keeps_what_was_said(gateway, searched):
    gateway.turn(
        *([{"type": "web"}] if searched else []),
        {"type": "text_delta", "text": "Tienes"},
        {"type": "error", "code": "assistant.provider_unavailable", "message": "x", "retriable": True},
    )
    frames = frames_of(**TURN)
    assert [frame["type"] for frame in frames] == ["text", "error", "done"]
    assert frames[1] == {"type": "error", "code": "assistant.provider_failed", "retriable": True}
    assert frames[-1]["append"] == [{"role": "assistant", "content": "Tienes"}]
    assert frames[-1]["web"] is searched


@SEARCHED
def test_a_connection_that_dies_half_way_is_said(gateway, searched):
    web = [{"type": "web"}] if searched else []
    gateway.turn(*web, {"type": "text_delta", "text": "Tienes"}, {"type": "text_delta", "text": " 3"}, cut_after=len(web) + 1)
    frames = frames_of(**TURN)
    assert [frame["type"] for frame in frames] == ["text", "error", "done"]
    assert frames[1]["code"] == "assistant.cut"
    assert frames[-1]["web"] is searched


def test_a_gateway_out_of_reach_is_said(settings):
    settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
    error = frames_of(**TURN)[-1]
    assert (error["type"], error["code"]) == ("error", "assistant.unreachable")


# ── Whether a turn brought pages of the web, for the report of its answer (hub#870, BASE-F105) ───────────────────────


def test_a_turn_that_brought_pages_of_the_web_says_so_when_it_closes(gateway):
    """The gateway's ``{type: web}`` comes before the text that uses the pages: the browser keeps it with the answer
    (``done.web``) and sends it back with a report, whose text erplora.com then does not mail (Brave's terms)."""
    gateway.turn(
        {"type": "web"},
        {"type": "text_delta", "text": "Según la AEAT, "},
        {"type": "text_delta", "text": "el plazo acaba el 20."},
        {"type": "response", "output": [], "usage": {}, "continuation": None},
    )
    frames = frames_of(**TURN)
    assert [frame["type"] for frame in frames] == ["text", "text", "done"]
    assert frames[-1]["web"] is True


def test_a_turn_without_pages_of_the_web_says_it_brought_none(gateway):
    """A ``false`` the Hub says, not one it leaves out: without it, a search turned on keeps every answer's text from
    support, also the ones that never searched."""
    gateway.turn({"type": "text_delta", "text": "Hola"}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    assert frames_of(**TURN)[-1]["web"] is False


def test_the_tools_it_asks_for_after_searching_still_say_the_pages(gateway):
    """A search, then a tool of the Hub: the mark closes the round that waits for the tool (the browser keeps it across
    the continuation)."""
    call = {"type": "function_call", "name": "demo__item__list", "call_id": "c1", "arguments": "{}"}
    gateway.turn({"type": "web"}, call, {"type": "response", "output": [call], "usage": {}, "continuation": "tok"})
    done = frames_of(**TURN)[-1]
    assert (done["pending"][0]["call_id"], done["continuation"], done["web"]) == ("c1", "tok", True)


def test_a_report_says_whether_its_answer_came_from_the_web(gateway):
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    assistant.gateway.report(A, message_id="m1", reason="incorrect", comment="", question="¿Plazo?", answer="El 20", web=True)
    assistant.gateway.report(A, message_id="m2", reason="incorrect", comment="", question="Hola", answer="Hola", web=False)
    first, second = gateway.sent("/internal/assistant/report")
    assert (first.body["web"], second.body["web"]) == (True, False)
    assert signed(first) and signed(second)


def test_a_report_that_does_not_know_leaves_the_web_out(gateway):
    """An answer kept before the mark existed: erplora.com's safe default decides (no text while its search is on), never
    a ``false`` the Hub made up."""
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    assistant.gateway.report(A, message_id="m1", reason="other", comment="", question="", answer="x", web=None)
    assert "web" not in gateway.sent("/internal/assistant/report")[0].body


# ── The web addresses erplora.com's own tools consulted, which the panel checks the answer's against (BASE-F99) ─────

LAW, RATE = "https://www.boe.es/doc", "https://frankfurter.dev"


def test_the_addresses_its_tools_consulted_close_the_round(gateway):
    gateway.turn(
        {"type": "sources", "sources": [LAW]},
        {"type": "text_delta", "text": "Según el BOE, sube."},
        {"type": "sources", "sources": [RATE]},
        {"type": "response", "output": [], "usage": {}, "continuation": None},
    )
    frames = frames_of(**TURN)
    assert [frame["type"] for frame in frames] == ["text", "done"]
    assert frames[-1]["sources"] == [LAW, RATE]


def test_a_round_whose_tools_consulted_nothing_says_none(gateway):
    gateway.turn({"type": "text_delta", "text": "Hola"}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    assert frames_of(**TURN)[-1]["sources"] == []


def test_what_was_consulted_before_a_failure_stays_with_what_was_said(gateway):
    gateway.turn(
        {"type": "sources", "sources": [LAW]},
        {"type": "text_delta", "text": "Según el BOE"},
        {"type": "error", "code": "assistant.provider_unavailable", "message": "x", "retriable": True},
    )
    assert frames_of(**TURN)[-1]["sources"] == [LAW]
