"""Schemas of the questions a run asks a person (``flow.question.*``, FLOW-F28 to F30) and of their answers."""

import datetime as dt
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.flow.schemas.fields import A_QUESTION, In, RunStatus, _text
from base.schemas.assistant import AssistantFieldOut


class QuestionListIn(In):
    pass


class QuestionRefIn(In):
    id: UUID = Field(
        title=gettext_noop("Question"),
        description="The question's id, from `flow.question.list`.",
        json_schema_extra=A_QUESTION,
    )


class AnswerIn(QuestionRefIn):
    approve: bool = Field(
        title=gettext_noop("Answer"),
        description="true: yes, the automation goes on; false: no, it does what its step says.",
    )
    note: _text(500) = Field("", description="A note for the history, optional.")


class QuestionOut(Schema):
    id: UUID
    flow_id: UUID
    flow_name: str
    run_id: UUID
    title: str
    details: str
    role: str = Field(description="Who it was asked of: '' whoever runs the business, `manager` or `employee`.")
    on_no: str
    on_timeout: str
    expires_at: dt.datetime
    created_at: dt.datetime
    action: str = Field(
        "",
        description="What the change the assistant wants in this step does, as the History names it, in the language "
        "of whoever asks («Cancel a reservation»); '' for a question an «Ask someone first» step asks.",
    )
    fields: list[AssistantFieldOut] = Field(
        default_factory=list,
        description="The data of the assistant's change in this step, as its confirmation card in the chat says "
        "them, read for whoever asks: a moment in their language at the business's hour, a record by its name only "
        "if they may read it, an amount in cents as `money`; none for a question an «Ask someone first» step asks.",
    )


class QuestionPageOut(Schema):
    rows: list[QuestionOut]


class AnsweredOut(Schema):
    id: UUID = Field(description="The question's id.")
    run_id: UUID
    status: RunStatus = Field(description="How its run is after the answer.")
