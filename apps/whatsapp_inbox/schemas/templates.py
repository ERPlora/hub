"""Schemas of the message templates: their list, how one reads, and writing one with Meta's rules."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import StringConstraints, ValidationInfo, field_validator

from apps.whatsapp_inbox.models.templates import NAMED_VARIABLE
from apps.whatsapp_inbox.schemas.fields import A_SAMPLE, A_TEMPLATE, TEMPLATE, Page, PageIn, _text
from apps.whatsapp_inbox.schemas.template_samples import TemplateSampleOut

TEMPLATE_NAME_RULE = _("Use lowercase letters, numbers and underscores only.")
TEMPLATE_LANGUAGE_RULE = _("Choose the template's language.")
TEMPLATE_NUMBERING = _("Number the variables 1, 2, 3… in order, without skipping any.")
TEMPLATE_EXAMPLES = _("Write an example for each variable.")
TEMPLATE_NO_VARIABLES = _("The header and the footer cannot have variables.")
TEMPLATE_FILE_NO_TEXT = _("A header with a photo, a video or a document has no text.")
BUTTON_URL = _("A link button needs an https:// address without variables.")
BUTTON_PHONE = _("A call button needs a number with its country code (+34…).")
BUTTON_KINDS = _("At most 2 link buttons and 1 call button.")
BUTTONS_GROUPED = _("Put the quick replies together, before or after the link and call buttons.")

TemplateCategory = Literal["UTILITY", "MARKETING", "AUTHENTICATION"]
#: What the Hub makes: an authentication template needs Meta's code button, made in WhatsApp Manager.
WritableCategory = Literal["UTILITY", "MARKETING"]
TemplateStatus = Literal[
    "DRAFT", "APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED", "DELETED"
]
HeaderFormat = Literal["", "TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION"]
#: What the form writes: none or a text (derived from ``header`` when empty), or a photo, a video or a document.
WritableHeaderFormat = Literal["", "TEXT", "IMAGE", "VIDEO", "DOCUMENT"]
FILE_HEADER_FORMATS = ("IMAGE", "VIDEO", "DOCUMENT")
SubmitState = Literal["", "queued", "sending", "failed"]

#: A variable of a template's text, as Meta writes it: ``{{1}}``.
TEMPLATE_VARIABLE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_ANY_VARIABLE = re.compile(r"\{\{.*?\}\}")


def template_variables(text: str) -> int:
    """How many variables ``text`` takes (the highest ``{{n}}``)."""
    return max((int(n) for n in TEMPLATE_VARIABLE.findall(text or "")), default=0)


class TemplateButtonIn(Schema):
    type: Literal["QUICK_REPLY", "URL", "PHONE_NUMBER"] = Field(
        description="QUICK_REPLY (an answer the customer taps), URL (opens a link) or PHONE_NUMBER (calls)."
    )
    text: _text(25, 1) = Field(description="What the button says, up to 25 characters.")
    url: _text(2000) = Field(
        "", validate_default=True, description="For URL: the https:// address it opens (no variables)."
    )
    phone_number: _text(16) = Field(
        "", validate_default=True, description="For PHONE_NUMBER: the number it calls, E.164 (+34910000000)."
    )

    @field_validator("url")
    @classmethod
    def _link(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("type") == "URL" and (not value.startswith("https://") or _ANY_VARIABLE.search(value)):
            raise ValueError(BUTTON_URL)
        return value if info.data.get("type") == "URL" else ""

    @field_validator("phone_number")
    @classmethod
    def _call(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("type") == "PHONE_NUMBER" and not re.fullmatch(r"\+[1-9]\d{6,14}", value):
            raise ValueError(BUTTON_PHONE)
        return value if info.data.get("type") == "PHONE_NUMBER" else ""


class TemplateWriteIn(Schema):
    """What the form writes of a template; the rules are Meta's, checked here to say them under each field."""

    category: WritableCategory = Field(
        "UTILITY", description="UTILITY (about something the customer asked or booked) or MARKETING (offers)."
    )
    header_format: WritableHeaderFormat = Field(
        "",
        description="Its header: empty or TEXT (the text of header, if any), or IMAGE, VIDEO or DOCUMENT with the file "
        "of header_sample.",
    )
    header: _text(60) = Field("", description="An optional title in bold, up to 60 characters, without variables.")
    header_sample: UUID | None = Field(
        None,
        description="For an IMAGE, VIDEO or DOCUMENT header: the id whatsapp_inbox.template_sample.upload answered "
        "for its file (Meta reviews the template with it; the same one again keeps it).",
        json_schema_extra=A_SAMPLE,
    )
    body: _text(1024, 1) = Field(description="The text, up to 1024 characters, with {{1}}, {{2}}… where the variables go.")
    body_examples: list[_text(1024)] = Field(
        default_factory=list, max_length=100, description="An example of each variable, in order: Meta reviews the template with them."
    )
    footer: _text(60) = Field("", description="An optional small line at the end, up to 60 characters, without variables.")
    buttons: list[TemplateButtonIn] = Field(
        default_factory=list, max_length=10,
        description="Up to 10 buttons: quick replies together, at most 2 links and 1 call.",
    )
    submit_key: UUID = Field(
        description="A key of the caller's own for THIS save (a new UUID per save, the same on a retry): saving "
        "again with it never registers the template twice.",
        json_schema_extra={"attempt_key": True},
    )

    @field_validator("header", "footer")
    @classmethod
    def _plain(cls, value: str, info: ValidationInfo) -> str:
        if _ANY_VARIABLE.search(value):
            raise ValueError(TEMPLATE_NO_VARIABLES)
        if info.field_name == "header" and value and info.data.get("header_format") in FILE_HEADER_FORMATS:
            raise ValueError(TEMPLATE_FILE_NO_TEXT)
        return value

    @field_validator("body")
    @classmethod
    def _numbered(cls, value: str) -> str:
        numbers = {int(n) for n in TEMPLATE_VARIABLE.findall(value)}
        if NAMED_VARIABLE.search(value) or (numbers and numbers != set(range(1, max(numbers) + 1))):
            raise ValueError(TEMPLATE_NUMBERING)
        return value

    @field_validator("body_examples")
    @classmethod
    def _examples(cls, value: list[str], info: ValidationInfo) -> list[str]:
        body = info.data.get("body")
        if body is not None and (len(value) != template_variables(body) or any(not example for example in value)):
            raise ValueError(TEMPLATE_EXAMPLES)
        return value

    @field_validator("buttons")
    @classmethod
    def _grouped(cls, value: list[TemplateButtonIn]) -> list[TemplateButtonIn]:
        kinds = [button.type for button in value]
        if kinds.count("URL") > 2 or kinds.count("PHONE_NUMBER") > 1:
            raise ValueError(BUTTON_KINDS)
        quick = [kind == "QUICK_REPLY" for kind in kinds]
        if sum(1 for before, after in zip(quick, quick[1:]) if before != after) > 1:
            raise ValueError(BUTTONS_GROUPED)
        return value


class TemplateCreateIn(TemplateWriteIn):
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=512)] = Field(
        description="Its name at Meta: lowercase letters, numbers and underscores (recordatorio_cita); it never changes."
    )
    language: Annotated[str, StringConstraints(strip_whitespace=True, max_length=15)] = Field(
        description="Its language code at Meta (es, es_ES, en_US, ca…); it never changes."
    )

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9_]+", value):
            raise ValueError(TEMPLATE_NAME_RULE)
        return value

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z]{2,3}(_[A-Z]{2,4})?", value):
            raise ValueError(TEMPLATE_LANGUAGE_RULE)
        return value


class TemplateUpdateIn(TemplateWriteIn):
    id: UUID = Field(
        title=TEMPLATE,
        description="The template's id in the Hub; its name and language do not change.",
        json_schema_extra=A_TEMPLATE,
    )


class TemplateRefIn(Schema):
    id: UUID = Field(title=TEMPLATE, description="The template's id in the Hub.", json_schema_extra=A_TEMPLATE)


class TemplateButtonOut(Schema):
    type: str = Field(description="QUICK_REPLY, URL, PHONE_NUMBER, or another of Meta's (made in WhatsApp Manager).")
    text: str = Field(description="What the button says.")
    url: str = Field("", description="The address a URL button opens.")
    phone_number: str = Field("", description="The number a PHONE_NUMBER button calls.")


class TemplateDraftOut(Schema):
    category: TemplateCategory = Field(description="The category of the edit.")
    header_format: HeaderFormat = Field("", description="The header type of the edit.")
    header: str = Field(description="The header of the edit.")
    header_sample: TemplateSampleOut | None = Field(None, description="The header's file of the edit.")
    body: str = Field(description="The text of the edit.")
    body_examples: list[str] = Field(description="Its examples.")
    footer: str = Field(description="Its footer.")
    buttons: list[TemplateButtonOut] = Field(description="Its buttons.")


class TemplateListIn(PageIn):
    search: _text(120) | None = Field(None, description="Part of the template's name.")
    status: TemplateStatus | None = Field(
        None, description="Only templates in this state at Meta (APPROVED to send)."
    )
    category: TemplateCategory | None = Field(
        None, description="Only UTILITY, MARKETING or AUTHENTICATION templates."
    )
    language: _text(15) | None = Field(
        None, description="Only templates in this language."
    )
    sendable: bool | None = Field(
        None,
        description="true: only the ones the Hub sends as they are, with nothing to choose (approved, not being "
        "deleted, a photo, video or document header only with its own file).",
    )
    fillable: bool | None = Field(
        None,
        description="true: the ones the inbox can send (approved, not being deleted), a photo, video or document "
        "header asking for its file when it has none of its own: also what an automation's «Send a message» step "
        "offers, with the file chosen in the step.",
    )


class TemplateOut(Schema):
    id: UUID = Field(description="The template's id in the Hub.")
    name: str = Field(description="Its name at Meta.")
    language: str = Field(description="Its language.")
    category: TemplateCategory = Field(
        description="UTILITY, MARKETING or AUTHENTICATION."
    )
    status: TemplateStatus = Field(description="What Meta says of it (DRAFT: Meta never had it).")
    header_format: HeaderFormat = Field(
        description="Its header: none, TEXT, IMAGE, VIDEO or DOCUMENT (a file), or LOCATION (made in WhatsApp Manager)."
    )
    header: str = Field(description="Its header text.")
    header_sample: TemplateSampleOut | None = Field(
        description="The file of its IMAGE, VIDEO or DOCUMENT header when it was chosen here (none for one made in "
        "WhatsApp Manager)."
    )
    body: str = Field(description="Its text, with {{1}}… where the variables go.")
    body_examples: list[str] = Field(description="An example of each variable.")
    footer: str = Field(description="Its footer.")
    buttons: list[TemplateButtonOut] = Field(description="Its buttons.")
    variables: int = Field(description="How many variables it takes.")
    rejected_reason: str = Field(description="Meta's reason when it rejected it.")
    meta_id: str = Field(description="Meta's id; empty while Meta never had it.")
    synced_at: datetime | None = Field(description="When erplora.com last reported it.")
    draft: TemplateDraftOut | None = Field(description="An edit waiting to reach Meta; the template above is what Meta has.")
    submit_state: SubmitState = Field(description="Its hand-over to Meta: queued, sending (to retry) or failed (fix it).")
    submit_error_code: str = Field(description="Why the last hand-over or deletion did not end well.")
    submit_error: str = Field(description="The reason, in words.")
    editable: bool = Field(description="Whether it can be changed here (else only in WhatsApp Manager).")
    sendable: bool = Field(
        description="Whether it goes as it is, with nothing to choose (a photo, video or document header only with its own "
        "file); one that asks for its file is still sent by the inbox and by an automation (fillable)."
    )
    supported: bool = Field(
        description="Whether the Hub fills it when sending, whatever Meta says of it (else it is only sent and "
        "changed from WhatsApp Manager: a file or place header, named variables, a code…)."
    )
    deleting: bool = Field(description="Deleted here, still being deleted at Meta.")


class TemplatePage(Page[TemplateOut]):
    pass


class TemplateNamedOut(Schema):
    """A template as its sheet names it: the same name may be in several languages."""

    id: UUID = Field(description="The template's id in the Hub.")
    name: str = Field(description="Its name at Meta.")
    language: str = Field(description="Its language.")
    label: str = Field(description="Its name and its language, as Settings › WhatsApp says it: «recordatorio (es)».")
