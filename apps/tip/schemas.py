"""Input and output schemas of the tips app's operations (OpenAPI, live params, 422 per field)."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, field_validator, model_validator

from apps.sale.schemas.fields import A_METHOD, A_SALE, AttemptKey, Cents, Closed, MethodType, Page, PageIn, PositiveCents
from base.schemas.assistant import names

#: How many suggestions each payment method offers at the charge.
SUGGESTIONS = 3

SAY_SALE_OR_POOL = _("Say the tip's sale, or that it goes to the pool.")
SAY_METHOD = _("Say the tip's payment method.")
POOL_IN_CASH = _("The pool takes cash: leave the payment method out.")
SAY_WHICH_TIP = _("Say which tip: its id or its sale's number.")
SAY_REASON = _("Write the reason.")
SAME_SUGGESTION = _("That suggestion is already there.")
SAY_PERCENT_OR_AMOUNT = _("Give each suggestion a percentage or an amount, not both.")
NOTHING_TO_CHANGE = _("Say what changes: the amount or the person.")

T_TIP = gettext_noop("Tip")
T_SALE = gettext_noop("Sale")
T_FOR = gettext_noop("For")
T_POOL = gettext_noop("To the pool")
A_MEMBER = names("staff.member.detail", name=("full_name",))
# The card names a tip by its sale's number, as the person does («the tip of 20261114-0007»).
A_TIP = names("tip.tip.get", name=("sale_number",))

SaleNumber = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=24)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Said = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Status = Literal["active", "voided"]


def _a_reason(value: str) -> str:
    if not value:
        raise ValueError(str(SAY_REASON))
    return value


# Settings


class Suggestion(Schema):
    """A percentage of the check's total before discounts, or an amount: one of the two."""

    percent: int | None = Field(None, ge=1, le=100, description="A percentage, 1 to 100.")
    amount: PositiveCents | None = Field(None, description="An amount, in cents.")

    @model_validator(mode="after")
    def _one_of_the_two(self):
        if (self.percent is None) == (self.amount is None):
            raise ValueError(str(SAY_PERCENT_OR_AMOUNT))
        return self


class MethodSuggestionsIn(Closed):
    method_id: UUID = Field(title=gettext_noop("Payment method"), json_schema_extra=A_METHOD)
    suggestions: list[Suggestion] = Field(
        min_length=SUGGESTIONS, max_length=SUGGESTIONS, description="Its three suggestions, in the order they show."
    )

    @field_validator("suggestions")
    @classmethod
    def _each_once(cls, suggestions: list[Suggestion]) -> list[Suggestion]:
        if len({(s.percent, s.amount) for s in suggestions}) < len(suggestions):
            raise ValueError(str(SAME_SUGGESTION))
        return suggestions


class SettingsPatchIn(Closed):
    """Only what is sent changes; ``null`` leaves a setting as it is."""

    enabled: bool | None = Field(None, description="Ask for a tip at the charge.")
    allow_custom: bool | None = Field(None, description="Allow another amount besides the suggestions.")
    preselected: int | None = Field(
        None, ge=0, le=SUGGESTIONS, description="Which suggestion comes chosen, 1 to 3; 0: «No tip»."
    )
    methods: list[MethodSuggestionsIn] | None = Field(
        None, description="The suggestions of each payment method sent; the others keep theirs."
    )


class MethodSuggestionsOut(Schema):
    method_id: UUID = Field(description="Sales' payment method.")
    method_name: str = Field(description="Its name in the reader's language.")
    method_type: MethodType = Field(description="cash, card, transfer or other.")
    suggestions: list[Suggestion] = Field(description="Its three suggestions.")


class SettingsOut(Schema):
    enabled: bool = Field(description="A tip is asked for at the charge.")
    allow_custom: bool = Field(description="Another amount is allowed besides the suggestions.")
    preselected: int = Field(description="Which suggestion comes chosen, 1 to 3; 0: «No tip».")
    methods: list[MethodSuggestionsOut] = Field(description="Every active payment method of Sales, with its suggestions.")


# What the charge proposes


class SuggestionIn(Closed):
    method_id: UUID = Field(
        title=gettext_noop("Payment method"), description="The payment method chosen.", json_schema_extra=A_METHOD
    )
    total: Cents = Field(description="The check's total before discounts, in cents: what a percentage is worked out on.")


class SuggestedTipOut(Schema):
    percent: int | None = Field(description="The percentage it is; empty when it is a fixed amount.")
    amount: int = Field(description="The tip it comes to, in cents.", json_schema_extra={"money": True})


class SuggestionOut(Schema):
    enabled: bool = Field(description="A tip is asked for at the charge; off, there is nothing to propose.")
    allow_custom: bool = Field(description="Another amount is allowed besides the suggestions.")
    preselected: int = Field(description="Which suggestion comes chosen, 1 to 3; 0: «No tip».")
    suggestions: list[SuggestedTipOut] = Field(description="The payment method's three, in their order; none when off.")


# Tips


class TipAddIn(Closed):
    """A tip of a sale, by its id or its number, with its payment method; or, with ``pool``, cash to the pool."""

    sale_id: UUID | None = Field(None, title=T_SALE, json_schema_extra=A_SALE)
    sale: SaleNumber | None = Field(None, title=T_SALE, description="The sale's number, when its id is not known.")
    pool: bool = Field(False, title=T_POOL, description="Cash to the pool, of no sale nor person (counted from the jar).")
    method_id: UUID | None = Field(None, description="Sales' payment method of the tip.", json_schema_extra=A_METHOD)
    method: Said | None = Field(None, description="Its name or its type (cash, card…), when its id is not known.")
    amount: PositiveCents = Field(description="The tip, in cents.")
    member_id: UUID | None = Field(
        None,
        title=T_FOR,
        description="Who it belongs to; empty: whoever served the sale.",
        json_schema_extra=A_MEMBER,
    )
    attempt_key: AttemptKey | None = Field(
        None, description="The charge's attempt key (with its leg): the same one records the tip once."
    )

    @model_validator(mode="after")
    def _sale_or_pool(self):
        named = self.sale_id is not None or self.sale is not None
        if named == self.pool:
            raise ValueError(str(SAY_SALE_OR_POOL))
        said_method = self.method_id is not None or self.method is not None
        if self.pool and said_method:
            raise ValueError(str(POOL_IN_CASH))
        if named and not said_method:
            raise ValueError(str(SAY_METHOD))
        return self


class TipRefIn(Closed):
    """A tip, by its id or by its sale's number (the one tip of that sale); the id wins."""

    id: UUID | None = Field(None, title=T_TIP, json_schema_extra=A_TIP)
    sale: SaleNumber | None = Field(None, title=T_SALE, description="Its sale's number, when its id is not known.")

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.sale is None:
            raise ValueError(str(SAY_WHICH_TIP))
        return self


class TipPatchIn(TipRefIn):
    amount: PositiveCents | None = Field(None, description="The right amount, in cents.")
    member_id: UUID | None = Field(None, title=T_FOR, description="Who it belongs to.", json_schema_extra=A_MEMBER)
    reason: Reason = Field(description="Why it changes.")

    _reason = field_validator("reason")(_a_reason)

    @model_validator(mode="after")
    def _something(self):
        if self.amount is None and self.member_id is None:
            raise ValueError(str(NOTHING_TO_CHANGE))
        return self


class TipVoidIn(TipRefIn):
    reason: Reason = Field(description="Why it is voided.")

    _reason = field_validator("reason")(_a_reason)


class TipListIn(PageIn):
    search: str | None = Field(None, max_length=120, description="A piece of the sale's number or of the person's name.")
    member_id: UUID | None = Field(None, title=T_FOR, description="Only this person's.", json_schema_extra=A_MEMBER)
    method_type: MethodType | None = Field(None, description="Only those paid that way.")
    status: Status | None = Field(None, description="active or voided.")
    date_from: date | None = Field(None, description="From this business day on.")
    date_to: date | None = Field(None, description="Up to this business day.")


class TipOut(Schema):
    id: UUID = Field(description="The tip's id.")
    sale_id: UUID | None = Field(description="Its sale; empty: to the pool.")
    sale_number: str = Field(description="Its sale's number.")
    pool: bool = Field(description="To the pool, of no sale.")
    member_id: UUID | None = Field(description="Who it belongs to; empty: unassigned.")
    member_name: str = Field(description="Their name.")
    method_id: UUID = Field(description="Its payment method.")
    method_name: str = Field(description="Its payment method's name.")
    method_type: MethodType = Field(description="cash, card, transfer or other.")
    amount: int = Field(description="In cents.", json_schema_extra={"money": True})
    status: Status = Field(description="active or voided.")
    created_at: datetime = Field(description="When it was recorded.")
    created_by: str = Field(description="Who recorded it.")
    adjusted_at: datetime | None = Field(description="When it was last adjusted.")
    adjusted_by: str = Field(description="Who adjusted it.")
    adjust_reason: str = Field(description="Why.")
    voided_at: datetime | None = Field(description="When it was voided.")
    voided_by: str = Field(description="Who voided it (or its sale).")
    void_reason: str = Field(description="Why.")


TipPage = Page[TipOut]


# Reactions to Sales' events


class Payload(Schema):
    """Another app's event payload: what this app reads of it (the rest is ignored)."""

    model_config = ConfigDict(extra="ignore")


class SaleVoidedIn(Payload):
    sale_id: UUID
    reason: str = ""
    voided_by: str = ""


class SaleRefundedIn(Payload):
    sale_id: UUID
    fully_refunded: bool = False
    reason: str = ""
    refunded_by: str = ""


class ReactionOut(Schema):
    changed: int = Field(description="How many tips the reaction voided.")
