"""«Read aloud» in the server's voice (round 2026-11-03n, PLAN-HUB §73): ``base.assistant.speak`` asks erplora.com
(``POST /internal/speech/synthesize``, signed as every ``/internal`` call) for the mp3 of an answer in the voice the
person chose, and ``POST /api/assistant/speak`` hands it to the panel as ``audio/mpeg``. When erplora.com cannot read
it (no voice configured, down, too slow), the Hub says so in its own envelope and the panel reads with the device's
voice instead. The gateway is ``fake_gateway`` (a real server): nothing of ours is patched.
"""

import base64
import json

import httpx
import pytest
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import OperationError, PermissionDenied
from live.operations import get
from pydantic import ValidationError

from base import assistant
from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
HOST = {"HTTP_HOST": "a.localhost:8000"}
EMPLOYEE = frozenset({"base.view_home", "demo.view"})
SYNTHESIZE = "/internal/speech/synthesize"
#: The first bytes of an mp3 (an ID3 header, then a frame's sync word).
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00\xff\xfb\x90d" + bytes(range(256))
XIMENA = "es-ES-Ximena:DragonHDLatestNeural"


@pytest.fixture(autouse=True)
def server_voice(settings):
    """The server's voice turned on (``ASSISTANT_SERVER_VOICE``), as a deployment with a voice provider has it; the
    default (off, round 2026-11-04a) is tested by name below."""
    settings.ASSISTANT_SERVER_VOICE = True


def ctx(permissions=EMPLOYEE, *, actor="ana", screen="es"):
    return OperationContext(scope=A, actor=actor, permissions=frozenset(permissions), language=screen)


def speak(permissions=EMPLOYEE, *, actor="ana", screen="es", **data):
    op = get("base.assistant.speak")
    return op(ctx(permissions, actor=actor, screen=screen), op.input.model_validate(data)).model_dump(mode="json")


def refused(status: int, code: str) -> dict:
    return {"status": status, "json": {"error": {"code": code, "message": "x"}}}


# ── The operation ────────────────────────────────────────────────────────────────────────────────────────────────


def test_reading_aloud_is_the_persons_and_never_a_tool_nor_a_transaction():
    op = get("base.assistant.speak")
    assert (op.kind, op.permission, op.database) == ("command", "base.view_home", False)
    assert not assistant.is_tool(op)
    with pytest.raises(PermissionDenied):
        speak(frozenset({"demo.view"}), text="Hola")


def test_an_answer_is_read_aloud_as_an_mp3_in_the_voice_chosen(gateway):
    gateway.reply(SYNTHESIZE, content=MP3, content_type="audio/mpeg")
    spoken = speak(text="  Tienes 3 mesas abiertas.  ", language="es", voice=XIMENA)
    assert spoken == {"content_type": "audio/mpeg", "content_base64": base64.b64encode(MP3).decode()}
    [seen] = gateway.sent(SYNTHESIZE)
    assert seen.body == {"hub": "a", "text": "Tienes 3 mesas abiertas.", "language": "es", "voice": XIMENA}
    assert signed(seen)


def test_the_audio_keeps_the_type_erplora_com_gives_it(gateway):
    """The contract is an mp3; another audio erplora.com answers is said as what it is, never relabelled."""
    gateway.reply(SYNTHESIZE, content=b"OggS" + bytes(32), content_type="audio/ogg")
    assert speak(text="Hola")["content_type"] == "audio/ogg"


def test_without_a_voice_erplora_com_reads_in_the_first_of_the_language(gateway):
    gateway.reply(SYNTHESIZE, content=MP3, content_type="audio/mpeg")
    speak(text="Hola")
    assert "voice" not in gateway.sent(SYNTHESIZE)[0].body


@pytest.mark.parametrize(
    ("asked", "screen", "sent"),
    [("", "es", "es"), ("", "en", "en"), ("es-ES", "en", "es"), ("en", "es", "en"), ("fr", "es", "en")],
)
def test_it_is_read_in_the_language_asked_else_the_screens_and_english_where_there_is_no_voice(gateway, asked, screen, sent):
    """The voices are Spanish and English (``@erplora/ui`` ``voices.ts``): a language without its own reads in English."""
    gateway.reply(SYNTHESIZE, content=MP3, content_type="audio/mpeg")
    speak(screen=screen, text="Hola", **({"language": asked} if asked else {}))
    assert gateway.sent(SYNTHESIZE)[0].body["language"] == sent


@pytest.mark.parametrize("text", ["a" * 4097, "", "   \n "], ids=["too_long", "empty", "blank"])
def test_a_text_too_long_or_with_nothing_to_read_is_refused_before_erplora_com_hears_it(gateway, text):
    with pytest.raises(ValidationError):
        get("base.assistant.speak").input.model_validate({"text": text})
    assert gateway.requests == []


def test_the_longest_text_read_at_once_is_erplora_coms_own_ceiling(gateway):
    gateway.reply(SYNTHESIZE, content=MP3, content_type="audio/mpeg")
    speak(text="a" * 4096)
    assert len(gateway.sent(SYNTHESIZE)[0].body["text"]) == 4096


@pytest.mark.parametrize("code", ["assistant.speech_unavailable", "assistant.provider_not_configured"])
def test_without_a_server_voice_it_says_it_is_not_available(gateway, code):
    """No key of the voices' provider on erplora.com: nothing to try again, the panel reads with the device's voice."""
    gateway.reply(SYNTHESIZE, **refused(503, code))
    with pytest.raises(OperationError) as caught:
        speak(text="Hola")
    assert (caught.value.status, caught.value.code) == (503, "base.assistant_speech_unavailable")


@pytest.mark.parametrize(
    ("status", "code"),
    [(422, "invalid_payload"), (429, "rate_limited"), (502, "assistant.provider_unavailable"), (500, "")],
)
def test_any_other_refusal_of_erplora_com_is_said_in_the_hubs_words(gateway, status, code):
    gateway.reply(SYNTHESIZE, **refused(status, code))
    with pytest.raises(OperationError) as caught:
        speak(text="Hola")
    assert (caught.value.status, caught.value.code) == (503, "base.assistant_speech_failed")


@pytest.mark.parametrize(
    "answer",
    [{"json": {"text": "Hola"}}, {"content": b"", "content_type": "audio/mpeg"}],
    ids=["json", "empty"],
)
def test_an_answer_that_is_no_audio_is_no_reading(gateway, answer):
    gateway.reply(SYNTHESIZE, **answer)
    with pytest.raises(OperationError) as caught:
        speak(text="Hola")
    assert (caught.value.status, caught.value.code) == (503, "base.assistant_speech_failed")


def test_its_refusals_are_said_in_the_persons_language(gateway):
    gateway.reply(SYNTHESIZE, **refused(503, "assistant.speech_unavailable"))
    gateway.reply(SYNTHESIZE, **refused(502, "assistant.provider_unavailable"))
    said = []
    with translation.override("es"):
        for _ in range(2):
            with pytest.raises(OperationError) as caught:
                speak(text="Hola")
            said.append(caught.value.message)
    assert said == [
        "La lectura en voz alta con la voz del servidor no está disponible.",
        "No se ha podido leer la respuesta en voz alta: inténtalo de nuevo.",
    ]


def test_with_the_server_voice_off_nothing_is_asked_of_erplora_com(settings, gateway):
    """Round 2026-11-04a: no voice provider for now, so the Hub never asks (the panel reads with the device's voice)."""
    settings.ASSISTANT_SERVER_VOICE = False
    with pytest.raises(OperationError) as caught:
        speak(text="Hola")
    assert (caught.value.status, caught.value.code) == (503, "base.assistant_speech_unavailable")
    assert gateway.requests == []


def test_erplora_com_slower_than_the_hub_waits_is_a_failure(gateway, monkeypatch):
    monkeypatch.setattr(assistant, "SPEECH_TIMEOUT", httpx.Timeout(0.2))
    gateway.reply(SYNTHESIZE, content=MP3, content_type="audio/mpeg", delay=1.0)
    with pytest.raises(OperationError) as caught:
        speak(text="Hola")
    assert (caught.value.status, caught.value.code) == (503, "base.assistant_speech_failed")


def test_erplora_com_out_of_reach_is_a_failure(settings):
    settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
    with pytest.raises(OperationError) as caught:
        speak(text="Hola")
    assert (caught.value.status, caught.value.code) == (503, "base.assistant_speech_failed")


def test_the_hub_waits_longer_than_erplora_com_waits_for_its_provider():
    """erplora.com waits up to 60 s for the voices' provider (saas ``assistant.media.TIMEOUT``): the Hub waits longer,
    so a slow provider comes back as erplora.com's own refusal, never as the Hub hanging up first."""
    assert assistant.SPEECH_TIMEOUT.read > 60


@pytest.mark.django_db(transaction=True)
def test_waiting_for_the_voice_holds_no_transaction(gateway, monkeypatch):
    """The till waits on the hub's connection (one transaction at a time on the Free plan, PLAN §14.2): none is open
    while erplora.com reads the answer."""
    gateway.reply(SYNTHESIZE, content=MP3, content_type="audio/mpeg")
    seen = []
    post = assistant._post_audio

    def probe(*args, **kwargs):
        seen.append(any(connection.in_atomic_block for connection in connections.all()))
        return post(*args, **kwargs)

    monkeypatch.setattr(assistant, "_post_audio", probe)
    speak(text="Hola")
    assert seen == [False]


# ── The route ────────────────────────────────────────────────────────────────────────────────────────────────────


def post(client, body, **extra):
    return client.post("/api/assistant/speak", json.dumps(body), content_type="application/json", **HOST, **extra)


def test_the_route_is_bound_to_its_operation():
    from base.api import router

    [route] = router.path_operations["/assistant/speak"].operations
    assert (route.methods, route.operation_id) == (["POST"], "base.assistant.speak")


def test_the_panel_gets_the_mp3_itself(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply(SYNTHESIZE, content=MP3, content_type="audio/mpeg")
    response = post(client, {"text": "Hola", "language": "es", "voice": XIMENA}, HTTP_ACCEPT="audio/mpeg")
    assert (response.status_code, response["Content-Type"], response.content) == (200, "audio/mpeg", MP3)
    assert response["Cache-Control"] == "no-store"
    # Through the operation and the signed door of erplora.com (here its fake, a real HTTP server).
    [seen] = gateway.sent(SYNTHESIZE)
    assert (seen.body["voice"], signed(seen)) == (XIMENA, True)


def test_an_integration_that_only_reads_json_gets_the_operations_output(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply(SYNTHESIZE, content=MP3, content_type="audio/mpeg")
    response = post(client, {"text": "Hola"}, HTTP_ACCEPT="application/json")
    assert response.json() == {"content_type": "audio/mpeg", "content_base64": base64.b64encode(MP3).decode()}


def test_without_the_server_voice_the_route_answers_the_envelope(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply(SYNTHESIZE, **refused(503, "assistant.speech_unavailable"))
    response = post(client, {"text": "Hola"}, HTTP_ACCEPT="audio/mpeg")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "base.assistant_speech_unavailable"


def test_with_the_server_voice_off_the_route_answers_the_envelope_without_asking(client, make_user, settings, gateway):
    settings.ASSISTANT_SERVER_VOICE = False
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = post(client, {"text": "Hola"}, HTTP_ACCEPT="audio/mpeg")
    assert (response.status_code, response.json()["error"]["code"]) == (503, "base.assistant_speech_unavailable")
    assert gateway.requests == []


@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize("on", [False, True])
def test_the_shell_tells_the_panel_whether_there_is_a_server_voice(client, make_user, settings, on):
    """The panel offers the server's voices (and asks the route) only when there is one; else it reads with the
    device's voice, without a choice of voice and without a request (``assistant-hub.ts`` ``hubAssistant``)."""
    from base.tests.test_spa import json_block

    settings.ASSISTANT_SERVER_VOICE = on
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    _, home = json_block(client.get("/demo/items", **HOST), "hub-home")
    assert home["server_voice"] is on


def test_nobody_without_a_session_has_anything_read(client, gateway):
    assert post(client, {"text": "Hola"}).status_code == 401
    assert gateway.requests == []


def test_a_text_too_long_is_refused_by_the_hub(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = post(client, {"text": "a" * 4097})
    assert response.status_code == 422
    assert "text" in response.json()["error"]["fields"]
    assert gateway.requests == []


def test_the_api_documents_the_mp3_and_the_json():
    """The OpenAPI document (and the Postman collection made from it) says both answers of a 200."""
    from config.api import api

    content = api.get_openapi_schema()["paths"]["/api/assistant/speak"]["post"]["responses"][200]["content"]
    assert content["audio/mpeg"]["schema"] == {"type": "string", "format": "binary"}
    assert content["application/json"]["schema"] == {"$ref": "#/components/schemas/AssistantSpeakOut"}
