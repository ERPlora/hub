"""The assistant's chat: a turn, a report, a transcription and speech (``base.assistant.*``).
"""

import base64
import contextlib
import dataclasses
import json

from django.conf import settings
from django.utils import timezone, translation
from django.utils.translation import gettext, pgettext
from live import assistant as shared
from live.context import OperationContext
from live.errors import OperationError, Unauthorized
from live.operations import get as get_operation
from live.operations import operation
from pydantic import ValidationError

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
NOT_AVAILABLE = "This tool is not available to this person here: nothing was done."
#: What the model hears on the last round of a request, the one that offers it no tool.
LAST_ROUND = (
    "This request has used all its steps: no more tools. Answer the person now: say what was done and what is left, "
    "for them to ask for it in another message."
)
#: What the model hears of a tool it asked for anyway after that round.
OUT_OF_STEPS = f"Nothing was done. {LAST_ROUND}"


def _assistant_screens(ctx: OperationContext, apps: dict) -> dict[str, str]:
    """The screens the assistant may link: the platform's and the menus of the apps on (``apps``), by name."""
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
        for config in apps.values():
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


def _assistant_asked(still_open: list[dict]) -> list[str]:
    """What the person wrote in the request still open (``_assistant_opened``), message by message. A file alone says
    nothing: the words written before it still count."""
    return [
        words
        for message in still_open
        if message.get("role") == "user" and (words := _assistant_words(message.get("content")))
    ]


def _assistant_opened(messages: list[dict], tools: dict) -> int:
    """Where the request still open starts: after the model last asked for a write, which closes what it was asked for,
    and never after the person's second-to-last message. The answers to the assistant's questions about a request name
    none of its tools («no tiene código, ponle tú uno»), so its first words must still count."""
    closed = max((at for at, message in enumerate(messages) if _asks_for_a_write(message, tools)), default=-1)
    said = [
        at
        for at, message in enumerate(messages)
        if message.get("role") == "user" and _assistant_words(message.get("content"))
    ]
    return min(closed + 1, said[-2]) if len(said) >= 2 else 0


def _asks_for_a_write(message: dict, tools: dict) -> bool:
    """Whether ``message`` is the model's asking for a write among ``tools``."""
    names = (function.get("name") for function in _functions(message))
    return any((op := shared.operation_of(str(name), tools)) is not None and op.kind == "command" for name in names)


def _functions(message: dict) -> list[dict]:
    """The tools the model asked for in ``message``, as the gateway wrote each: its ``name`` and ``arguments``."""
    calls = message.get("tool_calls") if message.get("role") == "assistant" else None
    asked = (call.get("function") for call in calls if isinstance(call, dict)) if isinstance(calls, list) else ()
    return [function for function in asked if isinstance(function, dict)]


def _assistant_searched(still_open: list[dict]) -> list[str]:
    """The tasks the model searched the person's tools for (``base.assistant.find_tools``) in the request still open
    (``_assistant_opened``), in order; a search its operation refuses searched nothing."""
    search = get_operation(assistant.relevance.FIND_TOOLS)
    queries = []
    for function in (function for message in still_open for function in _functions(message)):
        if function.get("name") != shared.tool_name(search.name):
            continue
        with contextlib.suppress(ValidationError):
            queries.append(search.input.model_validate_json(str(function.get("arguments") or "{}")).query)
    return queries


def _assistant_ran(ctx: OperationContext, tools: dict, call, outcome: "shared.ToolOutcome") -> dict:
    """What ran, or was refused, by its name: a write this person was not offered is named too. Named as its card
    names it: an app by its name, the platform by its screen; a failure says why."""
    op = shared.operation_of(call.name, tools) or shared.named(call.name)
    if op is None:
        named = {"name": call.name, "app": "", "app_name": "", "screen": "", "kind": ""}
    else:
        with translation.override(ctx.language):
            app_name = assistant.cards.app_name(op)
        screen = assistant.cards.screen(op)
        named = {"name": op.name, "app": op.app_label, "app_name": app_name, "screen": screen, "kind": op.kind}
    reason = assistant.failure_reason.reason(op, outcome, ctx.language)
    ran = {"call_id": call.call_id, **named, "outcome": outcome.outcome, "code": outcome.code, "reason": reason}
    return {**ran, **assistant.handed_files.receipt(outcome)}


@dataclasses.dataclass(frozen=True)
class _Calls:
    """What the calls of a turn run among: the person's tools and the files they attached, each by its name."""

    tools: dict
    files: dict[str, str]


def _assistant_answer(ctx, calls: _Calls, call, decision, *, stopped: bool):
    """Run one pending ``call`` (a read alone; a write with the person's yes, ``_assistant_write``) → ``(outcome,
    card, shown)``. What it gives the model tells its hours on the business's clock, the one the instructions name,
    never in UTC, and its amounts in their currency (``assistant.tools.run``)."""
    op = shared.operation_of(call.name, calls.tools)
    if op is None:
        return shared.refusal("refused", "not_available", NOT_AVAILABLE), None, ""
    if stopped:
        return shared.stopped(), None, ""
    try:
        arguments = None if op.kind == "query" else json.loads(call.arguments or "{}")
    except ValueError:
        arguments = None
    if not isinstance(arguments, dict):
        return assistant.handed_files.run(ctx, op, call.arguments), None, ""
    return _assistant_write(ctx, op, call, decision, calls.files)


def _assistant_given(ctx, op, arguments: dict, files: dict[str, str]):
    """``(given, None)``: what a write runs with, the model's data with the files they name
    (``assistant.attachments``); or ``(None, refusal)``: data the write would refuse, or a file not attached."""
    refused = shared.invalid_arguments(op, arguments)
    if refused is not None:
        return None, refused
    return assistant.attachments.with_files(op, arguments, files, ctx.language)


def _assistant_write(ctx, op, call, decision, files: dict[str, str]):
    """A write's ``(outcome, card, shown)``: the card when it still waits for its answer, with what it will do when its
    app declares a preview (BASE-F98), and the fingerprint of what it shows (``shown``, ``assistant.cards.fingerprint``);
    one that cannot be read is the write's outcome, and no card is shown. Neither is one for data the write would
    refuse: the model hears which (``invalid_payload``) and asks again with them corrected. The yes is for the card it
    answers (hub#1208): drawn again, a card that no longer shows what ``call.shown`` says — a record found by its name is
    another, a name or what it will do changed — runs nothing and is shown anew; a «no» or a word typed wrong never
    needs it. The card shows the model's data, a file by the name it was attached with; the write runs with the file."""
    arguments = json.loads(call.arguments or "{}")
    given, refused = _assistant_given(ctx, op, arguments, files)
    if refused is not None:
        return refused, None, ""
    found: list = []
    card = assistant.cards.card(op, arguments, ctx.language, ctx, found=found)
    answered = decision is not None and decision.call_id == call.call_id
    if card["blocked"] and not answered:
        return None, card, ""
    declined = shared.declined(card, decision) if answered else None
    if declined is not None:
        return declined, None, ""
    failure, preview = assistant.cards.preview(ctx, op, given, found=found)
    if failure is not None:
        return failure, None, ""
    drawn = {**card, "preview": preview}
    shown = assistant.cards.fingerprint(drawn, found)
    if not answered or call.shown != shown:
        return None, drawn, shown
    return assistant.tools.run(_assistant_approved(ctx, op, call.arguments), op, json.dumps(given)), None, ""


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
    read again, in ``setup``). The round that reaches ``shared.MAX_ROUNDS`` offers no tool, so the model answers with
    what was done and what is left; a tool it asks for anyway runs nothing (``_assistant_late``), and if it still asks
    for one after hearing so, the turn goes no further (``stop``)."""
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to talk to the assistant."))
    tools = assistant.tools.catalog(ctx)
    # The assistant's own search of the person's tools runs as one of them, but never ranks among them.
    runs = {**tools, assistant.relevance.FIND_TOOLS: get_operation(assistant.relevance.FIND_TOOLS)}
    calls = _Calls(tools=runs, files=assistant.attachments.attached(data.messages))
    append = _assistant_late(data.messages, data.pending)
    pending = [] if append else list(data.pending)
    decision = data.decision
    stopped = False
    executed: list[dict] = []
    card = None
    while pending:
        call = pending[0]
        outcome, card, shown = _assistant_answer(ctx, calls, call, decision, stopped=stopped)
        if outcome is None:
            # The call its card waits on goes back with what the card showed: the yes comes with it (hub#1208).
            pending[0] = call.model_copy(update={"shown": shown})
            break
        if decision is not None and decision.call_id == call.call_id:
            stopped = decision.stop
            decision = None
        append.append({"role": "tool", "tool_call_id": call.call_id, "content": outcome.content})
        executed.append(_assistant_ran(ctx, runs, call, outcome))
        pending.pop(0)
    messages = [*data.messages, *append]
    still_open = data.messages[_assistant_opened(data.messages, tools) :]
    business = _assistant_read(ctx, "base.business.get") or {}
    if card is not None:
        # The card paints an amount (its schema's ``money`` mark) in the business's currency, with its decimals.
        currency = business.get("currency") or "EUR"
        card["money"] = {"currency": currency, "decimals": business.get("currency_decimals", 2)}
    rounds = shared.rounds(messages)
    last = rounds >= shared.MAX_ROUNDS
    offered = [] if last else assistant.relevance.relevant(
        tools, _assistant_asked(still_open), ctx.language, searched=_assistant_searched(still_open)
    )
    text = _assistant_instructions(ctx, business, offered, setup=data.setup, last=last)
    stop = "assistant.too_many_steps" if rounds > shared.MAX_ROUNDS + 1 else ""
    return {
        # A file for a tool goes to the gateway by its name alone: the model never reads it.
        "messages": assistant.attachments.for_gateway(messages),
        "append": append,
        "executed": executed,
        "confirm": card,
        "pending": [p.model_dump() for p in pending],
        "tools": [shared.tool_spec(op) for op in offered],
        "instructions": text,
        "continuation": data.continuation,
        "stop": stop,
    }


def _assistant_late(messages: list[dict], pending: list) -> list[dict]:
    """What the model hears of the tools it asked for past the request's last round, the one that offered it none: they
    run nothing and show no card, nor a receipt (the person saw nothing), so it answers with what was done and what is
    left. None within the request's rounds."""
    if shared.rounds(messages) <= shared.MAX_ROUNDS:
        return []
    told = shared.refusal("refused", "base.assistant_out_of_steps", OUT_OF_STEPS).content
    return [{"role": "tool", "tool_call_id": call.call_id, "content": told} for call in pending]


def _assistant_instructions(ctx: OperationContext, business: dict, offered: list, *, setup: bool, last: bool) -> str:
    """The model's instructions for this round, with what it knows of the business (``assistant.business_facts``):
    to search before it says something cannot be done when the round offers the search (``prompt.SEARCH_FIRST``), with
    the checklist, read again, in ``setup``, and with ``LAST_ROUND`` on the last round of the request."""
    apps = assistant.tools.active_apps(ctx.scope)
    text = assistant.prompt.instructions(
        language=ctx.language,
        currency=business.get("currency") or "EUR",
        decimals=business.get("currency_decimals", 2),
        business=business.get("name") or "",
        screens=_assistant_screens(ctx, apps),
        role=_assistant_role(ctx),
        # What is offered without its permission is a write a manager may approve (``assistant.tools.catalog``).
        approvable=[op.name for op in offered if not ctx.has(op.permission)],
    )
    if any(op.name == assistant.relevance.FIND_TOOLS for op in offered):
        text += "\n" + assistant.prompt.SEARCH_FIRST
    text += "\n\n" + assistant.business_facts.block(ctx, business, apps, now=timezone.now())
    if setup:
        text += "\n\n" + assistant.prompt.setup_block(_assistant_read(ctx, "base.setup.status"))
    if last:
        text += "\n\n" + LAST_ROUND
    return text


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
