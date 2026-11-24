"""Schemas of the assistant (``base.assistant.*``, ``base.docs.search``), and the marks an app's
schemas give the data its card names (``names``, ``unless_given``, ``in_currency_of``), a file the person attaches in
the chat (``AN_ATTACHED_FILE``), a file a read hands the person (``A_HANDED_FILE``) and the names it reads
(``exactly_one``, ``RecordNameOut``)."""

from typing import Annotated, Any, Literal

from ninja import Schema
from pydantic import Field, StringConstraints, field_validator


def names(  # noqa: PLR0913
    read: str,
    by: str = "id",
    name: tuple[str, ...] = ("name",),
    *,
    within: tuple[str, ...] = (),
    as_said: bool = False,
    unless: tuple[str, ...] = (),
) -> dict:
    """The mark of a datum that names a record by its id (base/assistant/cards.py ``REFERS``): the assistant's card names it
    as ``read`` answers it (the first of ``name`` not empty), never by the id. ``within``: the data of its own object
    ``read`` takes beside it, when the record is found inside another (a course by its name with its menu; hub#1245).
    ``as_said``: a datum the person says in words, which the card says as said when it cannot be read (several fit,
    none does, nobody is at hand) rather than leaving it out; never an id (``base.E009``). ``unless``: the data of its
    own object any of which, when it comes, makes the write take its record by it and not by this datum (a course's
    menu said by its name beside the course's id): the card then neither reads nor shows it (hub#1250)."""
    refers: dict = {"read": read, "by": by, "name": list(name)}
    if within:
        refers["within"] = list(within)
    if as_said:
        refers["as_said"] = True
    if unless:
        refers["unless"] = list(unless)
    return {"refers": refers}


def unless_given(mark: dict, *data: str) -> dict:
    """``mark`` (``names``) left unread when any of ``data`` of its own object comes (``unless``): one mark declared
    once, beside the datum each object takes its record by instead (a course's ``id``, a menu's ``combo_id``)."""
    return {"refers": {**mark["refers"], "unless": list(data)}}


#: The mark of a datum that takes a whole file in base64 (base/assistant/attachments.py): from the chat, the model gives
#: the name of a file the person attached, and the turn gives the operation that file.
AN_ATTACHED_FILE: dict = {"attached_file": True}

#: The mark of the datum of a read's output that holds a whole file for the person (a CSV export), beside its
#: ``filename`` and ``content_type`` (base/assistant/handed_files.py): in the chat, the panel offers it to download and
#: the model hears its name.
A_HANDED_FILE: dict = {"handed_file": True}


def in_currency_of(read: str, by: str = "id", code: str = "currency") -> dict:
    """The mark of a datum that names a record in a currency of its own, a cart or a price list (base/assistant/cards.py
    ``CURRENCY``): the assistant's card says the amounts beside it in the currency ``read`` answers (its ``code``)."""
    return {"currency": {"read": read, "by": by, "code": code}}


def exactly_one(data: Any, message: Any) -> Any:
    """``data``, the input of an app's read of the names its assistant's card shows (``sale.record.get``,
    ``service.record.get``): one field per kind of record, of which exactly one is given; else ``message``, in the
    app's own words, refuses it (a 422). For a ``model_validator(mode="after")``."""
    if sum(getattr(data, name) is not None for name in type(data).model_fields) != 1:
        raise ValueError(str(message))
    return data


class RecordNameOut(Schema):
    """What an app's read of the names its assistant's card shows answers for a record (``exactly_one``)."""

    name: str = Field(description="What the screens of its app call it, in the reader's language.")



# ── Assistant ───────────────────────────────────────────────────────────────────────────────────────────────────


class AssistantCallIn(Schema):
    """A tool the model asked for, as the gateway gave it: its id, its name (``demo__item__create``) and its
    arguments as the model wrote them (JSON text); ``shown``, set by the Hub on the one whose card waits, the
    fingerprint of what that card showed, which the panel gives back with the calls that wait, so that the yes is
    for that card alone."""

    call_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    arguments: str = Field(default="{}", max_length=1_000_000)
    shown: str = Field(
        default="",
        max_length=64,
        description="The fingerprint of what the card of this call showed the person; empty while no card was drawn "
        "for it.",
    )


class AssistantDecisionIn(Schema):
    """The person's answer to the card of the first pending write: ``accepted``, what it typed when the card asks to
    type (a word, or how many) and ``stop`` («Cancel all»: this write and the rest of the turn)."""

    call_id: str = Field(min_length=1, max_length=200)
    accepted: bool
    typed: str = Field(default="", max_length=200)
    stop: bool = False


class AssistantTurnIn(Schema):
    """A turn of the assistant: the whole conversation (the person's browser keeps it), the tools the model asked for
    that still wait (``pending``) with their ``continuation``, the person's answer to the first one's card and whether
    the person is setting up the business (``setup``: the checklist goes to the model, read again)."""

    messages: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    continuation: str | None = Field(default=None, max_length=4096)
    pending: list[AssistantCallIn] = Field(default_factory=list, max_length=64)
    decision: AssistantDecisionIn | None = None
    setup: bool = False


class AssistantHandedFileOut(Schema):
    filename: str
    content_type: str
    content: str = Field(description="The whole file, as its screen's button saves it.")


class AssistantExecutedOut(Schema):
    call_id: str
    name: str = Field(description="The operation («demo.item.create»), or the tool's name when there was none.")
    app: str
    app_name: str = Field(
        description="Where it happened, in the person's language, as its card says it: the app's name, or the "
        "platform's screen («Settings»); empty when there was no operation."
    )
    screen: str = Field(
        default="",
        description="The platform's screen it happened on, by its key («settings»), for the receipt to name it in the "
        "language it is read in; empty for an app's (its menu names it).",
    )
    kind: Literal["query", "command", ""]
    outcome: Literal["ok", "error", "refused", "cancelled"]
    code: str
    reason: dict[str, str] = Field(
        default_factory=dict,
        description="Why it failed, for its receipt, keyed by the language it is said in («es»); empty unless it failed.",
    )
    file: AssistantHandedFileOut | None = Field(
        default=None, description="The file a read hands the person (a CSV export), to download under the answer."
    )


class AssistantMoneyOut(Schema):
    currency: str
    decimals: int


class AssistantFieldOut(Schema):
    name: str
    label: str
    kind: Literal["text", "money", "bool", "list", "object", "empty"]
    value: Any = None
    titled: bool = Field(
        default=False,
        description="Its label is the title its app wrote (a check, a table): the card calls it so over its own word "
        "for a datum it knows by its name.",
    )
    signed: bool = Field(
        default=False,
        description="An amount its app declares signed (a difference): written with its sign, «+» over.",
    )
    named: bool = Field(
        default=False,
        description="A list whose every item the server said in words (a record by its name, a moment, a value by its "
        "label, an amount): the card says its items; without it, how many it carries.",
    )
    money: AssistantMoneyOut | None = Field(
        default=None,
        description="The currency of an amount of a preview, as its read answers it (an invoice's); none = the "
        "business's, the card's own.",
    )


class AssistantCardOut(Schema):
    operation: str
    app: str
    app_name: str
    action: str
    risk: Literal["normal", "high"]
    fields: list[AssistantFieldOut]
    count: int | None = None
    confirm_word: str = Field(description="What to type to confirm a dangerous write; empty for a normal one.")
    blocked: bool = Field(description="A dangerous write that names no record: not done from the chat.")
    money: AssistantMoneyOut | None = Field(default=None, description="The business's currency, for its amounts.")
    preview: list[AssistantFieldOut] | None = Field(
        default=None,
        description="What a dangerous write will do, as the read its app declares answers it for this person; none "
        "when its app declares no preview.",
    )


class AssistantTurnOut(Schema):
    """The turn made ready (the route streams it, ``text/event-stream``): the tools' results to keep (``append``),
    what ran (``executed``), the card of the write that waits (``confirm``) with what still waits (``pending``), and
    what goes to the gateway (``messages``, ``tools``, ``instructions``, ``continuation``; no tool on the last round of
    the request); ``stop``, why it goes no further (``assistant.too_many_steps``)."""

    messages: list[dict[str, Any]]
    append: list[dict[str, Any]]
    executed: list[AssistantExecutedOut]
    confirm: AssistantCardOut | None = None
    pending: list[AssistantCallIn]
    tools: list[dict[str, Any]]
    instructions: str
    continuation: str | None = None
    stop: str = ""


class AssistantUsageIn(Schema):
    """No input: this business's allowance of the month."""


class AssistantUsageOut(Schema):
    used: int
    limit: int = Field(description="Messages of the month in the plan; 0: the plan has no assistant.")
    resets_at: str | None = Field(None, description="When the allowance comes back (UTC); none for a demo.")
    demo: bool


#: The most excerpts of ERPlora's documentation a search returns (erplora.com's own cap, saas ASSISTANT-F28).
DOCS_SEARCH_MAX = 12


class DocsSearchIn(Schema):
    """A question about how ERPlora works, in the person's words; ``limit`` excerpts at most (up to 12)."""

    query: str = Field(min_length=1, max_length=500, description="The how-to question, in the person's words.")
    limit: int = Field(
        default=8,
        ge=1,
        description=f"How many excerpts to return, at most {DOCS_SEARCH_MAX}.",
        json_schema_extra={"maximum": DOCS_SEARCH_MAX},
    )

    @field_validator("query")
    @classmethod
    def _something_asked(cls, query: str) -> str:
        query = query.strip()
        if not query:
            raise ValueError("ask something")
        return query

    @field_validator("limit")
    @classmethod
    def _capped(cls, limit: int) -> int:
        return min(limit, DOCS_SEARCH_MAX)


class DocsExcerptOut(Schema):
    """An excerpt of ERPlora's documentation that answers, with where it comes from to cite it."""

    source: str = Field(description="Where it comes from: help, app_doc (an app's documentation), workbook or plans.")
    path: str
    heading: str = Field(description="The headings it sits under, to cite it.")
    text: str
    score: float = Field(description="How close it is to the question: 1 the same meaning, 0 nothing in common.")
    lang: str
    #: Written by the Hub, not by erplora.com (hub#1079): the model ends its answer with it as it comes.
    cite: str = Field(
        default="",
        description="The line the answer ends with to say where it comes from: «Source: <its headings>», in the "
        "person's language.",
    )


class DocsSearchOut(Schema):
    results: list[DocsExcerptOut]


class FindToolsIn(Schema):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)] = Field(
        description="The task, in a few words: «list the products of a category», «create a product»."
    )


class FoundToolOut(Schema):
    name: str = Field(description="The tool's name, to call it.")
    description: str = Field(description="What the tool does.")


class FindToolsOut(Schema):
    tools: list[FoundToolOut] = Field(description="The tools found, best first.")


class AssistantReportIn(Schema):
    """What erplora.com's ``report`` door takes, with its limits: a long answer is reported whole."""

    message_id: str = Field(min_length=1, max_length=128)
    reason: Literal["incorrect", "harmful", "instructions", "other"]
    comment: str = Field(default="", max_length=20_000)
    question: str = Field(default="", max_length=200_000)
    answer: str = Field(min_length=1, max_length=200_000)
    #: Whether the answer's turn brought pages of the web (its ``done.web``): erplora.com then does not mail its text.
    #: None, a browser that does not know.
    web: bool | None = None


class AssistantReportOut(Schema):
    sent: bool
    duplicate: bool



class AssistantTranscribeIn(Schema):
    # 2 MB of audio is 2 796 204 characters of base64 (the gateway's own limit).
    audio: str = Field(min_length=1, max_length=2_800_000, description="The recording, in base64.")
    mime_type: str = Field(min_length=1, max_length=100)
    language: str = Field(default="", max_length=16)


class AssistantTranscribeOut(Schema):
    text: str
    language: str


#: The longest text read aloud at once: erplora.com's own ceiling (saas ``assistant.media.MAX_SPEECH_CHARS``).
MAX_SPEECH_CHARS = 4096


class AssistantSpeakIn(Schema):
    text: str = Field(min_length=1, max_length=MAX_SPEECH_CHARS, description="The text to read aloud.")
    language: str = Field(
        default="", max_length=16, description="es or en (es-ES too); empty: the screen's. Another one reads in English."
    )
    voice: str = Field(
        default="",
        max_length=64,
        description="A voice of erplora.com's engine; empty: its own for the language.",
    )

    @field_validator("text")
    @classmethod
    def _something_to_read(cls, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("write the text to read aloud")
        return text


class AssistantSpeakOut(Schema):
    content_type: str = Field(description="The audio's type: audio/mpeg.")
    content_base64: str = Field(description="The text read aloud, an mp3 in base64.")

