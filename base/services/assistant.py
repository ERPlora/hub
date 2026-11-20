"""The assistant's chat: a turn, a report, a transcription and speech (``base.assistant.*``).
"""

import base64
import dataclasses
import json

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext, pgettext
from live import assistant as shared
from live.context import OperationContext
from live.errors import OperationError, Unauthorized
from live.operations import get as get_operation
from live.operations import operation

from base import approvals as approval_rules
from base import assistant, queries
from base.models import Membership
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas.assistant import (
    AssistantReportIn,
    AssistantReportOut,
    AssistantSpeakIn,
    AssistantSpeakOut,
    AssistantTranscribeIn,
    AssistantTranscribeOut,
    AssistantTurnIn,
    AssistantTurnOut,
)

#: What the model hears of a tool that did not run (in English, as its instructions).
NOT_CONFIRMED = "Not confirmed by the person: nothing was done."
STOPPED = "The person stopped this request: nothing more was done."
NOT_AVAILABLE = "This tool is not available to this person here: nothing was done."
NOT_FROM_THE_CHAT = "This cannot be done from the chat (it names no record): nothing was done. Say where it is done."


def _assistant_screens(ctx: OperationContext) -> dict[str, str]:
    """The screens the assistant may link: the platform's and the menus of the apps on, by name."""
    with translation.override(ctx.language):
        screens = {
            "/": pgettext("base", "Home"),
            # In everybody's menu.
            "/employees": pgettext("base", "Employees"),
            "/apps": pgettext("base", "Apps"),
            "/settings": pgettext("base", "Settings"),
            "/profile": pgettext("base", "My profile"),
        }
        if ctx.has(ADMINISTER_HUB):
            screens["/system"] = pgettext("base", "System")
        if ctx.has(queries.files.VIEW_FILES):
            screens["/files"] = pgettext("base", "Files")
        for config in assistant.tools.active_apps(ctx.scope).values():
            for nav in getattr(config, "navigation", []) or []:
                screens.setdefault(nav.path, f"{config.verbose_name} › {nav.label}")
    return screens


def _assistant_read(ctx: OperationContext, name: str) -> dict | None:
    """``name``'s answer for the person (a read of base), or ``None`` when it fails: never made up."""
    op = get_operation(name)
    try:
        return op(ctx, op.input()).model_dump(mode="json")
    except OperationError:
        return None


def _assistant_words(content) -> str:
    """The words of a person's message, to choose its tools: a message that brings files comes as a list of parts,
    and only its text parts are words."""
    if isinstance(content, str):
        return content
    parts = content if isinstance(content, list) else []
    texts = (part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text")
    return "\n".join(str(text) for text in texts)


def _assistant_asked(messages: list[dict], tools: dict) -> list[str]:
    """What the person wrote in the request still open, message by message: everything since the model last asked for a
    write, which closes what it was asked for, and never fewer than their last two messages. The answers to the
    assistant's questions about a request name none of its tools («no tiene código, ponle tú uno»), so its first words
    must still count. A file alone says nothing: the words written before it still count."""
    closed = max((at for at, message in enumerate(messages) if _asks_for_a_write(message, tools)), default=-1)
    said = [
        (at, words)
        for at, message in enumerate(messages)
        if message.get("role") == "user" and (words := _assistant_words(message.get("content")))
    ]
    still_open = [words for at, words in said if at > closed]
    return still_open if len(still_open) >= 2 else [words for _, words in said[-2:]]


def _asks_for_a_write(message: dict, tools: dict) -> bool:
    """Whether ``message`` is the model's asking for a write among ``tools``."""
    calls = message.get("tool_calls") if message.get("role") == "assistant" else None
    asked = (call.get("function") for call in calls if isinstance(call, dict)) if isinstance(calls, list) else ()
    names = (function.get("name") for function in asked if isinstance(function, dict))
    return any((op := shared.operation_of(str(name), tools)) is not None and op.kind == "command" for name in names)


def _assistant_ran(ctx: OperationContext, tools: dict, call, outcome: "shared.ToolOutcome") -> dict:
    """What ran, or was refused, by its name: a write this person was not offered is named too. Named as its card
    names it: an app by its name, the platform by its screen."""
    op = shared.operation_of(call.name, tools) or shared.named(call.name)
    if op is None:
        named = {"name": call.name, "app": "", "app_name": "", "screen": "", "kind": ""}
    else:
        with translation.override(ctx.language):
            app_name = assistant.cards.app_name(op)
        screen = assistant.cards.screen(op)
        named = {"name": op.name, "app": op.app_label, "app_name": app_name, "screen": screen, "kind": op.kind}
    return {"call_id": call.call_id, **named, "outcome": outcome.outcome, "code": outcome.code}


def _assistant_refusal(outcome: str, code: str, message: str) -> "shared.ToolOutcome":
    """A tool that did not run, told to the model in the same envelope as an operation's error."""
    return shared.ToolOutcome(outcome, code, shared.error_content(code, message))


def _assistant_answer(ctx, tools, call, decision, *, stopped: bool):  # noqa: C901, PLR0911
    """Run one pending ``call`` (a read alone; a write with the person's yes) → ``(outcome, card, shown)``: the card
    when the write still waits for its answer, with what it will do when its app declares a preview (BASE-F98), and
    the fingerprint of what it shows (``shown``, ``assistant.cards.fingerprint``); one that cannot be read is the write's
    outcome, and no card is shown. Neither is one for data the write would refuse: the model hears which
    (``invalid_payload``) and asks again with them corrected. The yes is for the card it answers (hub#1208): drawn
    again, a card that no longer shows what ``call.shown`` says — a record found by its name is another, a name or what
    it will do changed — runs nothing and is shown anew; a «no» or a word typed wrong never needs it."""
    op = shared.operation_of(call.name, tools)
    if op is None:
        return _assistant_refusal("refused", "not_available", NOT_AVAILABLE), None, ""
    if stopped:
        return _assistant_refusal("cancelled", "base.assistant_stopped", STOPPED), None, ""
    if op.kind == "query":
        return shared.run_tool(ctx, op, call.arguments), None, ""
    try:
        arguments = json.loads(call.arguments or "{}")
    except ValueError:
        arguments = None
    if not isinstance(arguments, dict):
        return shared.run_tool(ctx, op, call.arguments), None, ""
    refused = shared.invalid_arguments(op, arguments)
    if refused is not None:
        return refused, None, ""
    found: list = []
    card = assistant.cards.card(op, arguments, ctx.language, ctx, found=found)
    answered = decision is not None and decision.call_id == call.call_id
    if card["blocked"]:
        if not answered:
            return None, card, ""
        return _assistant_refusal("cancelled", "base.assistant_not_from_chat", NOT_FROM_THE_CHAT), None, ""
    if answered and decision.stop:
        return _assistant_refusal("cancelled", "base.assistant_stopped", STOPPED), None, ""
    if answered and (not decision.accepted or not shared.confirmed(card, decision.typed)):
        return _assistant_refusal("cancelled", "base.assistant_not_confirmed", NOT_CONFIRMED), None, ""
    failure, preview = assistant.cards.preview(ctx, op, arguments, found=found)
    if failure is not None:
        return failure, None, ""
    drawn = {**card, "preview": preview}
    shown = assistant.cards.fingerprint(drawn, found)
    if not answered or call.shown != shown:
        return None, drawn, shown
    return shared.run_tool(_assistant_approved(ctx, op, call.arguments), op, call.arguments), None, ""


def _assistant_approved(ctx: OperationContext, op, arguments: str) -> OperationContext:
    """Who runs a write the person said yes to: the person. When they may not and a manager may approve it
   , the turn asks as the screen does — ``requires_elevation`` for this very request — and, repeated with
    the pass, runs it with that one permission more; the pass is spent in the write's own transaction
    (``base.approval_spend``), so a write that fails leaves it unspent and one that ran cannot run twice. The question
    says the figures of that write, read from its ``arguments`` as the command validates them."""
    request = getattr(ctx, "request", None)
    if ctx.has(op.permission) or request is None or approval_rules.approvable(op.name) is None:
        return ctx
    asked = approval_rules.fingerprint(request, ctx.scope.key)
    figures = approval_rules.figures_from(op, arguments)
    token = request.headers.get(approval_rules.HEADER, "")
    if not token.startswith(approval_rules.TOKEN_PREFIX):
        raise approval_rules.refusal(op.name, asked, figures, ctx.scope)
    request.approved = approval_rules.Approved(
        operation=op.name, permission=op.permission, token=token, fingerprint=asked, figures=figures
    )
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) | {op.permission})


@operation(
    "base.assistant.turn",
    kind="command",
    permission=VIEW_HOME,
    input=AssistantTurnIn,
    output=AssistantTurnOut,
    ai={"description": "Not an assistant tool (the assistant's own turn: the person writes it in its panel)."},
)
def assistant_turn(ctx: OperationContext, data: AssistantTurnIn) -> dict:
    """A turn of the Hub's assistant made ready: the reads the model asked for run as the
    person; a write shows its card and runs only with the person's yes (``decision``; «Cancel all» = ``stop``), and
    only on what that card showed (hub#1208: the call it waits on goes back with its ``shown``); a tool this person
    was not offered never runs. Then what goes to the gateway: the tools of what was asked, by relevance,
    and the instructions (with the person's role and the writes a manager must approve, hub#585; with the checklist,
    read again, in ``setup``). Past ``shared.MAX_ROUNDS`` rounds of tools it goes no further (``stop``)."""
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to talk to the assistant."))
    tools = assistant.tools.catalog(ctx)
    pending = list(data.pending)
    decision = data.decision
    stopped = False
    append: list[dict] = []
    executed: list[dict] = []
    card = None
    while pending:
        call = pending[0]
        outcome, card, shown = _assistant_answer(ctx, tools, call, decision, stopped=stopped)
        if outcome is None:
            # The call its card waits on goes back with what the card showed: the yes comes with it (hub#1208).
            pending[0] = call.model_copy(update={"shown": shown})
            break
        if decision is not None and decision.call_id == call.call_id:
            stopped = decision.stop
            decision = None
        append.append({"role": "tool", "tool_call_id": call.call_id, "content": outcome.content})
        executed.append(_assistant_ran(ctx, tools, call, outcome))
        pending.pop(0)
    messages = [*data.messages, *append]
    asked = _assistant_asked(data.messages, tools)
    business = _assistant_read(ctx, "base.business.get") or {}
    if card is not None:
        # The card paints an amount (its schema's ``money`` mark) in the business's currency, with its decimals.
        currency = business.get("currency") or "EUR"
        card["money"] = {"currency": currency, "decimals": business.get("currency_decimals", 2)}
    offered = assistant.relevance.relevant(tools, asked, ctx.language)
    text = assistant.prompt.instructions(
        language=ctx.language,
        currency=business.get("currency") or "EUR",
        decimals=business.get("currency_decimals", 2),
        business=business.get("name") or "",
        screens=_assistant_screens(ctx),
        role=_assistant_role(ctx),
        # What is offered without its permission is a write a manager may approve (``assistant.tools.catalog``).
        approvable=[op.name for op in offered if not ctx.has(op.permission)],
    )
    if data.setup:
        text += "\n\n" + assistant.prompt.setup_block(_assistant_read(ctx, "base.setup.status"))
    stop = ""
    if card is None and not stopped and shared.rounds(messages) >= shared.MAX_ROUNDS:
        stop = "assistant.too_many_steps"
    return {
        "messages": messages,
        "append": append,
        "executed": executed,
        "confirm": card,
        "pending": [p.model_dump() for p in pending],
        "tools": [shared.tool_spec(op) for op in offered],
        "instructions": text,
        "continuation": data.continuation,
        "stop": stop,
    }


def _assistant_role(ctx: OperationContext) -> str:
    """The role in this business of whom the assistant serves (hub#585): their ``Membership``'s; "" for an actor with
    none here (an API key, ERPlora's staff)."""
    if not hasattr(ctx.actor, "get_username"):
        return ""
    return Membership.objects.filter(user=ctx.actor, host=ctx.scope.key).values_list("role", flat=True).first() or ""


def _gateway_failure(code: str, message: str) -> OperationError:
    """erplora.com did not do it (unreachable, down, refused): a 503 the panel says in its own words."""
    return OperationError(message, code=code, status=503)


@operation(
    "base.assistant.report",
    kind="command",
    permission=VIEW_HOME,
    input=AssistantReportIn,
    output=AssistantReportOut,
    ai={"description": "Not an assistant tool (the person reports an answer of the assistant from its panel)."},
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def assistant_report(ctx: OperationContext, data: AssistantReportIn) -> dict:
    """Send erplora.com's team an answer the person reports, with the question that led to it."""
    try:
        return assistant.gateway.report(ctx.scope, **data.model_dump())
    except assistant.gateway.GatewayError:
        raise _gateway_failure(
            "base.assistant_report_not_sent", gettext("The report could not be sent: try again in a moment.")
        ) from None


@operation(
    "base.assistant.transcribe",
    kind="command",
    permission=VIEW_HOME,
    input=AssistantTranscribeIn,
    output=AssistantTranscribeOut,
    ai={"description": "Not an assistant tool (the person's dictation in the panel, turned into text it reviews)."},
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def assistant_transcribe(ctx: OperationContext, data: AssistantTranscribeIn) -> dict:
    """The text of the person's dictation, by erplora.com: it goes to the box, never sent by itself."""
    try:
        return assistant.gateway.transcribe(ctx.scope, audio=data.audio, mime_type=data.mime_type, language=data.language or ctx.language)
    except assistant.gateway.GatewayError as exc:
        if exc.status == 413 or exc.code == "payload_too_large":
            raise OperationError(
                gettext("The recording is too long: dictate a shorter message."), code="base.assistant_audio_too_long", status=413
            ) from None
        raise _gateway_failure(
            "base.assistant_transcribe_failed", gettext("The audio could not be transcribed: try again.")
        ) from None


#: erplora.com has no voice to read with (no key of the voices' provider): nothing to try again.
SPEECH_NOT_CONFIGURED = frozenset({"assistant.speech_unavailable", "assistant.provider_not_configured"})


def _speech_unavailable() -> OperationError:
    return _gateway_failure(
        "base.assistant_speech_unavailable", gettext("Reading aloud in the server's voice is not available.")
    )


@operation(
    "base.assistant.speak",
    kind="command",
    permission=VIEW_HOME,
    input=AssistantSpeakIn,
    output=AssistantSpeakOut,
    ai={"description": "Not an assistant tool (the panel reads an answer aloud in the server's voice the person chose)."},
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def assistant_speak(ctx: OperationContext, data: AssistantSpeakIn) -> dict:
    """An answer read aloud in the server's voice, by erplora.com: the mp3. When it cannot, the panel reads with the
    device's voice. With no server voice (``ASSISTANT_SERVER_VOICE`` off) erplora.com is never asked."""
    if not settings.ASSISTANT_SERVER_VOICE:
        raise _speech_unavailable()
    try:
        spoken = assistant.gateway.speak(ctx.scope, text=data.text, language=data.language or ctx.language, voice=data.voice)
    except assistant.gateway.GatewayError as exc:
        if exc.code in SPEECH_NOT_CONFIGURED:
            raise _speech_unavailable() from None
        raise _gateway_failure(
            "base.assistant_speech_failed", gettext("The answer could not be read aloud: try again.")
        ) from None
    return {"content_type": spoken["content_type"], "content_base64": base64.b64encode(spoken["audio"]).decode()}
