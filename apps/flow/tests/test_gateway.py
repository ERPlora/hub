"""erplora.com's assistant door for an automation's step (FLOW-F39): ``POST /internal/assistant/chat``, the turn
answered at once, signed as every ``/internal`` call. What a failure is: retried when the SaaS says it can be
(``retriable``, a rate limit, a door that could not be reached), up to three tries; final otherwise."""

import pytest

from apps.flow import gateway as flow_gateway
from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

CHAT = "/internal/assistant/chat"


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    monkeypatch.setattr(flow_gateway, "PAUSES", (0, 0))


def ask(**more):
    return flow_gateway.turn("a.erplora.com", messages=[{"role": "user", "content": "Hi"}], tools=[], instructions="Be brief", **more)


def test_a_turn_is_its_words_its_tools_and_its_continuation(gateway):
    gateway.reply(
        CHAT,
        json={
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "Let me look"}]},
                {"type": "function_call", "call_id": "c1", "name": "task__task__list", "arguments": "{}"},
            ],
            "continuation": "tok",
        },
    )
    answer = ask(continuation="before")
    assert (answer.text, answer.continuation) == ("Let me look", "tok")
    assert answer.calls == [{"call_id": "c1", "name": "task__task__list", "arguments": "{}"}]
    [seen] = gateway.sent(CHAT)
    assert signed(seen)
    assert seen.body == {
        "hub": "a.erplora.com",
        "messages": [{"role": "user", "content": "Hi"}],
        "tools": [],
        "instructions": "Be brief",
        "continuation": "before",
    }


@pytest.mark.parametrize(
    ("status", "error", "code"),
    [
        (429, {"code": "assistant.quota_exceeded", "retriable": False}, "assistant.quota_exceeded"),
        (502, {"code": "assistant.provider_rejected", "retriable": False}, "assistant.provider_rejected"),
        (403, {"code": "hub_inactive"}, "hub_inactive"),
        (503, {"code": "assistant.no_model", "retriable": False}, "assistant.no_model"),
    ],
)
def test_what_waiting_does_not_mend_is_not_tried_again(gateway, status, error, code):
    gateway.reply(CHAT, status=status, json={"error": {"message": "x", **error}})
    with pytest.raises(flow_gateway.Failed) as failed:
        ask()
    assert (failed.value.code, failed.value.retriable) == (code, False)
    assert len(gateway.sent(CHAT)) == 1


@pytest.mark.parametrize(
    "reply",
    [
        {"status": 502, "json": {"error": {"code": "assistant.provider_unavailable", "retriable": True}}},
        {"status": 429, "json": {"error": {"code": "rate_limited"}}, "headers": {"Retry-After": "1"}},
        {"status": 500, "json": None},
    ],
)
def test_what_may_mend_is_tried_three_times_in_all(gateway, reply):
    for _ in range(3):
        gateway.reply(CHAT, **reply)
    with pytest.raises(flow_gateway.Failed) as failed:
        ask()
    assert failed.value.retriable
    assert len(gateway.sent(CHAT)) == 3


def test_a_second_try_that_answers_is_the_answer(gateway):
    gateway.reply(CHAT, status=502, json={"error": {"code": "assistant.provider_unavailable", "retriable": True}})
    gateway.reply(CHAT, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": "Hi"}]}]})
    assert ask().text == "Hi"


def test_a_door_that_cannot_be_reached_is_unreachable(settings):
    settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
    settings.INTERNAL_SHARED_SECRET = "s"
    with pytest.raises(flow_gateway.Failed) as failed:
        ask()
    assert (failed.value.code, failed.value.retriable) == ("assistant.unreachable", True)
