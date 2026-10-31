"""What the Hub's log says when erplora.com's assistant does not answer (saas#167; BASE-F94, BASE-F106).

The panel says every failure in a few words of its own («The assistant is not available right now…», «The audio could
not be transcribed…»), so the reason lives only in the log: each failed call to the gateway leaves one line with its
door, the business, the HTTP status and the gateway's code — or that it never got there, and how. Never what the
person said, dictated or was answered. On 30/10 a production without providers answered 503 ``assistant.no_model``
and ``assistant.provider_not_configured`` to every turn and dictation, and the Hub said nothing of it.
"""

import asyncio
import logging

import pytest
from live.context import Scope

from base import assistant
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

A = Scope("host", "a")
QUESTION = "cuanto vendi hoy en la mesa 4"
AUDIO = "UklGRiQAAABXQVZFZm10IBAAAAABAAEA"
TURN_PATH = "/internal/assistant/chat/stream"
TRANSCRIBE_PATH = "/internal/speech/transcribe"


def frames_of(**kwargs):
    async def collect():
        return [frame async for frame in assistant.stream_turn(A, **kwargs)]

    return asyncio.run(collect())


TURN = {"messages": [{"role": "user", "content": QUESTION}], "tools": [], "instructions": "x", "continuation": None}


def lines(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "base.assistant"]


def only_line(caplog) -> str:
    found = lines(caplog)
    assert len(found) == 1, [record.getMessage() for record in found]
    assert found[0].levelno == logging.WARNING
    return found[0].getMessage()


def says_nothing_of_the_person(caplog) -> None:
    assert QUESTION not in caplog.text and AUDIO not in caplog.text


@pytest.fixture
def caplog(caplog):
    caplog.set_level(logging.INFO, logger="base.assistant")
    return caplog


# ── A refusal: the door, the business, the status and the gateway's code ────────────────────────────────────────


@pytest.mark.parametrize(
    "status, code",
    [
        (503, "assistant.no_model"),
        (503, "assistant.provider_not_configured"),
        (401, "unauthorized"),
        (403, "hub_inactive"),
        (429, "rate_limited"),
    ],
)
def test_a_refused_turn_leaves_its_door_status_and_code(gateway, caplog, status, code):
    gateway.reply(TURN_PATH, status=status, json={"error": {"code": code, "message": "x"}})
    assert frames_of(**TURN)[-1]["type"] == "error"
    line = only_line(caplog)
    assert line.startswith("base.assistant.gateway_refused ")
    assert f"path={TURN_PATH}" in line and "hub=a" in line and f"status={status}" in line and f"code={code}" in line
    says_nothing_of_the_person(caplog)


def test_a_refusal_with_no_envelope_still_says_its_status(gateway, caplog):
    """A proxy's 502 page, not the gateway's JSON: its status is all there is to say."""
    gateway.reply(TURN_PATH, status=502, json=None)
    frames_of(**TURN)
    line = only_line(caplog)
    assert "status=502" in line and "code=-" in line


@pytest.mark.parametrize(
    "door, path",
    [
        (lambda: assistant.transcribe(A, audio=AUDIO, mime_type="audio/webm", language="es"), TRANSCRIBE_PATH),
        (lambda: assistant.usage(A), "/internal/assistant/usage"),
        (
            lambda: assistant.report(A, message_id="m1", reason="other", comment="", question=QUESTION, answer="x"),
            "/internal/assistant/report",
        ),
    ],
)
def test_a_refused_door_leaves_its_door_status_and_code(gateway, caplog, door, path):
    gateway.reply(path, status=503, json={"error": {"code": "assistant.provider_not_configured", "message": "x"}})
    with pytest.raises(assistant.GatewayError):
        door()
    line = only_line(caplog)
    assert line.startswith("base.assistant.gateway_refused ")
    assert f"path={path}" in line and "hub=a" in line and "status=503" in line
    assert "code=assistant.provider_not_configured" in line
    says_nothing_of_the_person(caplog)


# ── Never reached: the door and the kind of failure ──────────────────────────────────────────────────────────────


def test_a_turn_that_never_reaches_erplora_says_how(settings, caplog):
    settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
    assert frames_of(**TURN)[-1]["code"] == "assistant.unreachable"
    line = only_line(caplog)
    assert line.startswith("base.assistant.gateway_unreachable ")
    assert f"path={TURN_PATH}" in line and "hub=a" in line and "kind=ConnectError" in line


def test_a_dictation_that_never_reaches_erplora_says_how(settings, caplog):
    settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
    with pytest.raises(assistant.GatewayError):
        assistant.transcribe(A, audio=AUDIO, mime_type="audio/webm", language="es")
    line = only_line(caplog)
    assert line.startswith("base.assistant.gateway_unreachable ")
    assert f"path={TRANSCRIBE_PATH}" in line and "kind=ConnectError" in line
    says_nothing_of_the_person(caplog)


# ── Half way: the provider's failure, or a turn cut short ────────────────────────────────────────────────────────


def test_a_provider_failing_half_way_leaves_its_code(gateway, caplog):
    gateway.turn(
        {"type": "text_delta", "text": "Tienes"},
        {"type": "error", "code": "assistant.provider_unavailable", "message": "x", "retriable": True},
    )
    frames_of(**TURN)
    line = only_line(caplog)
    assert line.startswith("base.assistant.gateway_failed ")
    assert f"path={TURN_PATH}" in line and "code=assistant.provider_unavailable" in line and "retriable=True" in line
    assert "Tienes" not in caplog.text


def test_a_turn_cut_short_is_said(gateway, caplog):
    gateway.turn({"type": "text_delta", "text": "Tienes"}, {"type": "text_delta", "text": " 3"}, cut_after=1)
    assert any(frame.get("code") == "assistant.cut" for frame in frames_of(**TURN))
    line = only_line(caplog)
    assert line.startswith("base.assistant.gateway_cut ") and f"path={TURN_PATH}" in line and "hub=a" in line
    assert "kind=no_done" in line
    assert "Tienes" not in caplog.text


def test_a_turn_broken_half_way_says_how(gateway, caplog):
    """The connection breaks after the first words (the body is shorter than it announced): cut, and by what."""
    gateway.turn(
        {"type": "text_delta", "text": "Tienes"},
        {"type": "text_delta", "text": " 3"},
        cut_after=1,
        headers={"Content-Length": "100000"},
    )
    assert any(frame.get("code") == "assistant.cut" for frame in frames_of(**TURN))
    line = only_line(caplog)
    assert line.startswith("base.assistant.gateway_cut ") and "kind=RemoteProtocolError" in line
    assert "Tienes" not in caplog.text


# ── What works says nothing ──────────────────────────────────────────────────────────────────────────────────────


def test_an_answered_turn_and_dictation_leave_no_line(gateway, caplog):
    gateway.turn({"type": "text_delta", "text": "Hola"}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    gateway.reply(TRANSCRIBE_PATH, json={"text": "hola", "language": "es"})
    frames_of(**TURN)
    assistant.transcribe(A, audio=AUDIO, mime_type="audio/webm", language="es")
    assert lines(caplog) == []
