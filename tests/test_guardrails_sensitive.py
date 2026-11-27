"""Guardrail of the sensitive data: a cost or someone's contact details in an answer carries its data permission.

live gives a field marked ``json_schema_extra={"requires": "<permission>"}`` as null to whoever lacks the permission, on
every door (``live.sensitive``; the marks of base are in ``base.sensitive``). A field left unmarked reaches every role
that may open its operation. Here:

- every field of every operation's answer, at any depth, whose name says it is sensitive (:data:`SENSITIVE_WORDS`)
  carries a mark or is in :data:`UNMARKED`, closed and with its reason; what the list names must still exist and still
  be unmarked, so it never rots, and each reason is held to what it promises;
- a read whose answer marks a field cannot be filtered or sorted by it without the same mark on the input, which live
  then refuses to whoever lacks it: sorting by cost would tell the order of the costs;
- every amount a figures read answers (a period's totals, a summary, the close by person) carries a mark, or the read
  is in :data:`UNMARKED_FIGURES`, closed and with its reason, each held to what it promises.
"""

import inspect
from collections.abc import Callable, Iterable, Iterator
from typing import Any, Literal, get_args, get_origin

import pytest
from live.operations import Operation, registry
from live.sensitive import marked_fields, required_permission
from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo

from apps.staff.models import Member
from base.queries.ownership import Owned
from base.sensitive import COSTS, CUSTOMER_CONTACT

#: The words of a field's name that say it carries a cost or someone's contact details or pay. A name matches when one
#: of them is a whole part of it between underscores: ``unit_cost`` and ``customer_email`` do, ``costume`` does not.
#: What the comps cost the business is a cost too (``gift_total``); whether a line is one (``is_gift``) is not.
SENSITIVE_WORDS = (
    "cost", "margin", "email", "phone", "commission", "salary", "wage", "stock_value", "hourly_rate", "gift_total",
    "total_gifts",
)

# ── Why a sensitive-sounding field may go unmarked ────────────────────────────────────────────────────────────────

#: A setting, a count or a flag about the data, not the data.
ABOUT_THE_DATA = "about the data"
#: The business's own address or number, which it publishes itself.
BUSINESS_OWN = "the business's own"
#: The caller's own record, which its operation only ever gives to that person.
CALLERS_OWN = "the caller's own"
#: Pay that only reaches whoever holds ``staff.view_compensation``: every operation answering it requires it.
COMPENSATION_ONLY = "compensation only"
#: Pay a person reads only on their own line, and everyone's only with ``staff.view_compensation``: every operation
#: answering it reads its rows through a declaration of whose they are (``Owned``) whose «see all» is that permission.
OWN_LINE = "the caller's own line"
#: Still reaches every role that opens its operation: its app marks it with its data permission (hub#2048).
NOT_MARKED_YET = "not marked yet"

COMPENSATION = "staff.view_compensation"

#: Every unmarked field of an answer whose name says it is sensitive: ``<module>.<Schema>.<field>`` → why. Closed on
#: purpose: a new one gets its mark, or comes here with a reason a reviewer can weigh.
UNMARKED: dict[str, str] = {
    "apps.cart_checkout.schemas.CartDetailOut.customer_email": NOT_MARKED_YET,
    "apps.cart_checkout.schemas.CartOut.customer_email": NOT_MARKED_YET,
    "apps.cart_checkout.schemas.OrderOut.customer_email": NOT_MARKED_YET,
    "apps.inventory.schemas.stock.SummaryOut.products_without_cost": ABOUT_THE_DATA,
    "apps.online_booking.schemas.public.PageOut.require_email": ABOUT_THE_DATA,
    "apps.online_booking.schemas.settings.SettingsOut.require_email": ABOUT_THE_DATA,
    "apps.reservation.schemas.settings.SettingsOut.require_email": ABOUT_THE_DATA,
    "apps.reservation.schemas.settings.SettingsOut.require_phone": ABOUT_THE_DATA,
    "apps.staff.schemas.commissions.CommissionOut.commission_rate": COMPENSATION_ONLY,
    "apps.staff.schemas.commissions.CommissionReportOut.total_commission": OWN_LINE,
    "apps.staff.schemas.commissions.CommissionReportRow.commission": OWN_LINE,
    "apps.staff.schemas.commissions.CommissionReportRow.commission_rate": OWN_LINE,
    "apps.staff.schemas.members.CompensationOut.commission_rate": COMPENSATION_ONLY,
    "apps.staff.schemas.members.CompensationOut.hourly_rate": COMPENSATION_ONLY,
    "apps.staff.schemas.members.MemberMineOut.commission_rate": CALLERS_OWN,
    "apps.staff.schemas.members.MemberMineOut.email": CALLERS_OWN,
    "apps.staff.schemas.members.MemberMineOut.hourly_rate": CALLERS_OWN,
    "apps.staff.schemas.members.MemberMineOut.phone": CALLERS_OWN,
    "apps.website.schemas.ContactSection.email": BUSINESS_OWN,
    "apps.website.schemas.ContactSection.phone": BUSINESS_OWN,
    "apps.whatsapp_inbox.schemas.channel.ChannelConnectOut.phone_number": BUSINESS_OWN,
    "apps.whatsapp_inbox.schemas.channel.ChannelOut.phone_number": BUSINESS_OWN,
    "apps.whatsapp_inbox.schemas.conversations.ByPhoneOut.phone_is_international": ABOUT_THE_DATA,
    "apps.whatsapp_inbox.schemas.templates.TemplateButtonOut.phone_number": BUSINESS_OWN,
    "base.schemas.profile.ProfileOut.contact_email": CALLERS_OWN,
}

#: The operations that answer a caller's own record, which ``CALLERS_OWN`` stands on.
OWN_RECORD_OPERATIONS = frozenset({"base.profile.get", "base.profile.update", "staff.member.mine"})


# ── What the checks read ───────────────────────────────────────────────────────────────────────────────────────────


def sensitive_name(name: str) -> bool:
    padded = f"_{name}_"
    return any(f"_{word}_" in padded for word in SENSITIVE_WORDS)


def schemas_in(annotation: Any) -> Iterator[type[BaseModel]]:
    """The schemas a field's type names: itself, or inside ``X | None``, ``list[X]``, ``dict[str, X]``…"""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    for argument in get_args(annotation):
        yield from schemas_in(argument)


def fields_of(schema: type[BaseModel]) -> Iterator[tuple[type[BaseModel], str, FieldInfo]]:
    """Every field of ``schema`` and of the schemas inside it, at any depth, each schema once."""
    seen: set[type[BaseModel]] = set()
    pending = [schema]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        for name, field in current.model_fields.items():
            yield current, name, field
            pending.extend(schemas_in(field.annotation))


def key(schema: type[BaseModel], name: str) -> str:
    return f"{schema.__module__}.{schema.__qualname__}.{name}"


def unmarked_sensitive(operations: Iterable[Operation]) -> dict[str, set[str]]:
    """``<module>.<Schema>.<field>`` → the operations whose answer carries it, for every sensitive-sounding field of an
    answer that has no mark."""
    found: dict[str, set[str]] = {}
    for operation in operations:
        for schema, name, field in fields_of(operation.output):
            if sensitive_name(name) and required_permission(field) is None:
                found.setdefault(key(schema, name), set()).add(operation.name)
    return found


def literal_values(annotation: Any) -> Iterator[str]:
    """The texts a ``Literal`` inside ``annotation`` allows (an order's keys, with their leading ``-``)."""
    if get_origin(annotation) is Literal:
        yield from (value for value in get_args(annotation) if isinstance(value, str))
        return
    for argument in get_args(annotation):
        yield from literal_values(argument)


def names_a(marked: str, name: str) -> bool:
    return name == marked or name.startswith(f"{marked}_") or name.endswith(f"_{marked}")


def unguarded_filters(operation: Operation) -> list[str]:
    """The input fields of a read that filter or sort by a field its answer marks, without the mark themselves."""
    if operation.kind != "query":
        return []
    marked = {mark.name for mark in marked_fields(operation.output)}
    answered = {name for _, name, _ in fields_of(operation.output)} if marked else set()
    found = []
    for schema, name, field in fields_of(operation.input):
        if not marked or required_permission(field) is not None:
            continue
        # The choices of a filter called as a field of the answer are that field's values («came by phone» is a
        # source); the choices of any other input are the keys of an order.
        sorted_by = set() if name in answered else {value.lstrip("-") for value in literal_values(field.annotation)}
        if any(names_a(term, name) for term in marked) or sorted_by & marked:
            found.append(f"{operation.name}: {key(schema, name)}")
    return found


# ── The Hub's operations ───────────────────────────────────────────────────────────────────────────────────────────


def test_every_sensitive_field_of_an_answer_is_marked_or_listed_with_its_reason():
    unlisted = sorted(set(unmarked_sensitive(registry.values())) - set(UNMARKED))
    assert unlisted == [], (
        "Mark these with their data permission (base.sensitive: COSTS, CUSTOMER_CONTACT, TEAM_CONTACT, "
        "BUSINESS_TOTALS), or list them in UNMARKED with their reason:\n" + "\n".join(unlisted)
    )


def test_what_the_list_names_still_exists_and_is_still_unmarked():
    assert sorted(set(UNMARKED) - set(unmarked_sensitive(registry.values()))) == []


def test_every_reason_is_one_of_the_known_ones():
    known = {ABOUT_THE_DATA, BUSINESS_OWN, CALLERS_OWN, COMPENSATION_ONLY, NOT_MARKED_YET, OWN_LINE}
    assert {name: reason for name, reason in UNMARKED.items() if reason not in known} == {}


def test_pay_listed_as_compensation_only_is_answered_only_to_who_may_see_it():
    found = unmarked_sensitive(registry.values())
    answered_by = {name for field, reason in UNMARKED.items() if reason == COMPENSATION_ONLY for name in found[field]}
    assert {name: registry[name].permission for name in answered_by if registry[name].permission != COMPENSATION} == {}


def reads_lines_of_the_pay(fn: Callable) -> bool:
    """Whether ``fn`` reads its rows through a declaration of its module (``Owned``) whose «see all» is the pay."""
    source = inspect.getsource(fn)
    declared = [
        name
        for name, value in vars(inspect.getmodule(fn)).items()
        if isinstance(value, Owned) and value.all_permission == COMPENSATION
    ]
    return any(f"{name}.counted(" in source or f"{name}.visible(" in source for name in declared)


def test_pay_listed_as_ones_own_line_is_read_through_a_declaration_of_the_pay():
    found = unmarked_sensitive(registry.values())
    answered_by = {name for field, reason in UNMARKED.items() if reason == OWN_LINE for name in found[field]}
    assert answered_by  # positive control: the commission lines are answered
    assert sorted(name for name in answered_by if not reads_lines_of_the_pay(registry[name].fn)) == []


def test_a_callers_own_field_is_answered_only_by_an_operation_of_their_own_record():
    found = unmarked_sensitive(registry.values())
    answered_by = {name for field, reason in UNMARKED.items() if reason == CALLERS_OWN for name in found[field]}
    assert answered_by <= OWN_RECORD_OPERATIONS


def test_no_read_filters_or_sorts_by_a_marked_field_without_its_mark():
    assert [found for operation in registry.values() for found in unguarded_filters(operation)] == []


# ── The figures ────────────────────────────────────────────────────────────────────────────────────────────────────

#: The words of a read's action that say it answers figures, as whole parts between underscores; a read in a
#: ``figures`` or ``stats`` module answers figures too (Sales' «today» and «last 7 days»).
FIGURE_WORDS = ("stats", "summary", "figures", "report", "by_staff", "totals")

#: Adds up only the rows the caller counts (``Owned.counted``): the whole business's with its «see all» permission and
#: ``base.view_business_totals``, else the caller's own.
COUNTED = "counted by whose it is"
#: The money of one register session, which whoever closes it counts: never a figure of the whole business.
ONE_SESSION = "one session's"

#: Every figures read that answers an amount without a mark → why. Closed on purpose: a new one marks its amounts
#: (``BUSINESS_TOTALS`` for the whole business's), or comes here with a reason a reviewer can weigh.
UNMARKED_FIGURES: dict[str, str] = {
    "cash_register.session.closing_summary": ONE_SESSION,
    "sale.sale.by_staff": COUNTED,
    "sale.sale.last_7_days": COUNTED,
    "sale.sale.stats": COUNTED,
    "sale.sale.today": COUNTED,
    "staff.commission.report": COUNTED,
}


def answers_figures(operation: Operation) -> bool:
    action = f"_{operation.name.rsplit('.', 1)[-1]}_"
    module = operation.fn.__module__.rsplit(".", 1)[-1]
    return operation.kind == "query" and (module in ("figures", "stats") or any(f"_{w}_" in action for w in FIGURE_WORDS))


def unmarked_amounts(operations: Iterable[Operation]) -> dict[str, list[str]]:
    """Each figures read → the amounts of its answer, at any depth, that carry no mark."""
    found = {}
    for operation in filter(answers_figures, operations):
        amounts = [
            key(schema, name)
            for schema, name, field in fields_of(operation.output)
            if isinstance(field.json_schema_extra, dict)
            and field.json_schema_extra.get("money")
            and required_permission(field) is None
        ]
        if amounts:
            found[operation.name] = sorted(amounts)
    return found


def test_every_amount_of_a_figures_read_is_marked_or_its_read_is_listed_with_its_reason():
    unlisted = {name: amounts for name, amounts in unmarked_amounts(registry.values()).items() if name not in UNMARKED_FIGURES}
    assert unlisted == {}, "Mark these amounts (base.sensitive: BUSINESS_TOTALS…), or list the read in UNMARKED_FIGURES"


def test_what_the_figures_list_names_still_answers_an_unmarked_amount():
    assert sorted(set(UNMARKED_FIGURES) - set(unmarked_amounts(registry.values()))) == []


def test_every_figures_reason_is_one_of_the_known_ones():
    known = {COUNTED, ONE_SESSION, COMPENSATION_ONLY}
    assert {name: reason for name, reason in UNMARKED_FIGURES.items() if reason not in known} == {}


def test_a_read_listed_as_counted_adds_up_what_the_caller_counts():
    listed = [name for name, reason in UNMARKED_FIGURES.items() if reason == COUNTED]
    assert [name for name in listed if ".counted(" not in inspect.getsource(registry[name].fn)] == []


def test_a_read_listed_as_one_session_is_asked_for_one():
    listed = [name for name, reason in UNMARKED_FIGURES.items() if reason == ONE_SESSION]
    assert [name for name in listed if "session_id" not in registry[name].input.model_fields] == []


def test_a_figures_read_listed_as_compensation_only_requires_it():
    listed = [name for name, reason in UNMARKED_FIGURES.items() if reason == COMPENSATION_ONLY]
    assert {name: registry[name].permission for name in listed if registry[name].permission != COMPENSATION} == {}


class PeriodTotalsOut(BaseModel):
    count: int = 0
    revenue: int = Field(0, json_schema_extra={"money": True})


class DaysOut(BaseModel):
    rows: list[PeriodTotalsOut] = []


class MarkedTotalsOut(BaseModel):
    count: int = 0
    stock_value: int | None = Field(None, json_schema_extra={"money": True, **COSTS})


def test_an_unmarked_amount_of_a_figures_read_is_caught_at_any_depth():
    assert unmarked_amounts([operation("shop.sale.stats", PeriodTotalsOut), operation("shop.sale.by_staff", DaysOut)]) == {
        "shop.sale.stats": [key(PeriodTotalsOut, "revenue")],
        "shop.sale.by_staff": [key(PeriodTotalsOut, "revenue")],
    }


def test_a_marked_amount_or_a_read_that_is_not_of_figures_is_not():
    assert unmarked_amounts([operation("shop.sale.stats", MarkedTotalsOut)]) == {}
    assert unmarked_amounts([operation("shop.sale.list", PeriodTotalsOut)]) == {}
    assert unmarked_amounts([operation("shop.sale.stats", PeriodTotalsOut, kind="command")]) == {}


# ── The checks catch what they guard ───────────────────────────────────────────────────────────────────────────────


class LineOut(BaseModel):
    name: str = ""
    unit_cost: int | None = None


class LinesOut(BaseModel):
    rows: list[LineOut] = []
    supplier_email: str = ""
    costume: str = ""


class MarkedLineOut(BaseModel):
    unit_cost: int | None = Field(None, json_schema_extra=COSTS)


class MarkedLinesOut(BaseModel):
    rows: list[MarkedLineOut] = []


class LineListIn(BaseModel):
    unit_cost_min: int | None = None
    sort: Literal["name", "-unit_cost"] = "name"
    search: str = ""


class GuardedLineListIn(BaseModel):
    unit_cost_min: int | None = Field(None, json_schema_extra=COSTS)
    sort: Literal["name", "-unit_cost"] = Field("name", json_schema_extra=COSTS)
    search: str = ""


def operation(name: str, output: type[BaseModel], input: type[BaseModel] = LineListIn, kind: str = "query") -> Operation:
    return Operation(name=name, kind=kind, permission=None, input=input, output=output, expose_api=False, ai=None,
                     fn=lambda ctx, data: {})


def test_an_unmarked_cost_or_contact_is_caught_at_any_depth_and_a_lookalike_is_not():
    found = unmarked_sensitive([operation("stock.line.list", LinesOut)])
    assert set(found) == {key(LineOut, "unit_cost"), key(LinesOut, "supplier_email")}
    assert found[key(LineOut, "unit_cost")] == {"stock.line.list"}


def test_a_marked_one_is_not():
    assert unmarked_sensitive([operation("stock.line.list", MarkedLinesOut)]) == {}


@pytest.mark.parametrize(
    "name", ["unit_cost", "customer_email", "phone_number", "total_commission", "stock_value", "gift_total", "total_gifts"]
)
def test_the_sensitive_words_match_whole_parts_of_a_name(name):
    assert sensitive_name(name)


@pytest.mark.parametrize("name", ["costume", "emails_sent_count_x", "telephone", "commissioning", "is_gift", "gift_reason"])
def test_and_only_whole_parts(name):
    assert not sensitive_name(name)


#: Planted declarations: one of the pay, and one whose «see all» is reading the team.
PAY_LINES = Owned(Member, all_permission=COMPENSATION, mine=lambda person: None)
TEAM_LINES = Owned(Member, all_permission="staff.view", mine=lambda person: None)


def lines_through_the_pay(ctx):
    return PAY_LINES.counted(ctx)


def lines_through_reading_the_team(ctx):
    return TEAM_LINES.visible(ctx)


def every_line(ctx):
    return Member.objects.all()


def test_a_read_of_ones_own_line_is_told_from_one_that_skips_the_declaration_of_the_pay():
    assert reads_lines_of_the_pay(lines_through_the_pay)
    assert not reads_lines_of_the_pay(lines_through_reading_the_team)
    assert not reads_lines_of_the_pay(every_line)


def test_filtering_or_sorting_by_a_marked_field_without_its_mark_is_caught():
    assert unguarded_filters(operation("stock.line.list", MarkedLinesOut)) == [
        f"stock.line.list: {key(LineListIn, 'unit_cost_min')}",
        f"stock.line.list: {key(LineListIn, 'sort')}",
    ]


class MarkedContactOut(BaseModel):
    phone: str | None = Field(None, json_schema_extra=CUSTOMER_CONTACT)
    source: Literal["walk_in", "phone"] = "walk_in"


class OrderedContactListIn(BaseModel):
    order: Literal["name", "phone"] = "name"


class SourceListIn(BaseModel):
    source: Literal["walk_in", "phone"] | None = None


def test_a_filter_whose_choices_name_a_marked_field_is_not_an_order():
    # «Came by phone» is a source, not the customer's phone: the filter chooses among the values of the answer's
    # ``source``.
    assert unguarded_filters(operation("shop.contact.list", MarkedContactOut, SourceListIn)) == []


def test_an_order_by_a_marked_field_is_caught_whatever_its_field_is_called():
    assert unguarded_filters(operation("shop.contact.list", MarkedContactOut, OrderedContactListIn)) == [
        f"shop.contact.list: {__name__}.OrderedContactListIn.order"
    ]


def test_with_its_mark_or_on_a_write_or_on_an_unmarked_answer_it_is_not():
    assert unguarded_filters(operation("stock.line.list", MarkedLinesOut, GuardedLineListIn)) == []
    assert unguarded_filters(operation("stock.line.create", MarkedLinesOut, kind="command")) == []
    assert unguarded_filters(operation("stock.line.list", LinesOut)) == []
