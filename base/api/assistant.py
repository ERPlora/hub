"""Routes of the assistant, a report to support and a pass to erplora.com."""

import base64

from live.ninja import bind, run_operation
from ninja import Router
from ninja.decorators import decorate_view

from django.http import HttpResponse

from base import assistant, queries, services
from base.request_body import accept_body_up_to
from base.schemas.assistant import AssistantReportIn, AssistantSpeakIn, AssistantTranscribeIn, AssistantTurnIn
from base.schemas.support import SaasPassIn, SupportReportIn

router = Router()


#: A turn's body: the conversation and the attachments of its last question, in base64 (the gateway takes 32 MB).
MAX_ASSISTANT_TURN_BODY = 32 * 1024 * 1024
#: A dictation: 2 MB of audio in base64 and its JSON around it.
MAX_ASSISTANT_AUDIO_BODY = 3_000_000


# The 200 is a stream (text/event-stream) of the turn's frames (base/assistant/gateway.py ``turn_frames``), not the JSON of
# its operation's output, which is what the stream is made of.
@bind(router, "base.assistant.turn", "/assistant/turn")
@decorate_view(accept_body_up_to(MAX_ASSISTANT_TURN_BODY))
async def assistant_turn(request, data: AssistantTurnIn):
    # What its tools wait on erplora.com for (a search in ERPlora's documentation, this month's messages) goes before
    # its transaction.
    with assistant.gateway.prepared(await assistant.gateway.prepare(request, data)):
        plan = await run_operation(request, services.assistant.assistant_turn, data)
    return assistant.gateway.turn_response(request, plan.model_dump(mode="json"))


@bind(router, "base.assistant.usage", "/assistant/usage")
async def assistant_usage(request):
    return await run_operation(request, queries.assistant.assistant_usage)


@bind(router, "base.assistant.report", "/assistant/report")
async def assistant_report(request, data: AssistantReportIn):
    return await run_operation(request, services.assistant.assistant_report, data)


@bind(router, "base.support.report", "/support/report")
async def support_report(request, data: SupportReportIn):
    return await run_operation(request, services.support.support_report, data)


@bind(router, "base.saas_pass.create", "/saas-pass")
async def saas_pass_create(request, data: SaasPassIn):
    return await run_operation(request, services.support.saas_pass_create, data)


@bind(router, "base.assistant.transcribe", "/assistant/transcribe")
@decorate_view(accept_body_up_to(MAX_ASSISTANT_AUDIO_BODY))
async def assistant_transcribe(request, data: AssistantTranscribeIn):
    return await run_operation(request, services.assistant.assistant_transcribe, data)


# The panel plays the mp3 itself (a ``blob:`` of the answer, CSP ``media-src``); an integration that accepts only JSON
# gets the operation's output, the mp3 in base64. A refusal is the error envelope either way.
@bind(
    router,
    "base.assistant.speak",
    "/assistant/speak",
    openapi_extra={
        "responses": {
            200: {
                "description": "The text read aloud: the mp3, or the operation's JSON when only JSON is accepted.",
                "content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}},
            }
        }
    },
)
async def assistant_speak(request, data: AssistantSpeakIn):
    spoken = await run_operation(request, services.assistant.assistant_speak, data)
    accepts = request.headers.get("Accept", "")
    if "application/json" in accepts and "audio/mpeg" not in accepts:
        return spoken
    return HttpResponse(
        base64.b64decode(spoken.content_base64), content_type=spoken.content_type, headers={"Cache-Control": "no-store"}
    )
