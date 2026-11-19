"""What the app of a write reads before the Hub's assistant shows its card (``base/assistant/cards.py``,
``base/assistant/checks.py``): what a dangerous write will do (its preview) and the check that refuses its data
first, each run as the person and checked at start."""

import json

import pytest
from live import assistant as shared
from live.errors import OperationError
from live.operations import Operation, get, registry
from ninja import Field, Schema
from pydantic import ConfigDict

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import ctx, shown, titled
from base.tests.card_values import assert_a_sent_amount_is_in_the_business_currency

__all__ = ["in_business_a"]


@HUB_DB
def test_a_title_the_read_of_a_preview_wrote_is_marked_so_too(settle):
    """What a dangerous write will do (BASE-F98) is said as what it sends: the read titles its owner and its person."""
    failure, fields = assistant.cards.preview(ctx(language="es"), settle, {"id": "7"})
    assert failure is None
    assert titled(fields) == {"asked_by": True, "name": True, "total_cents": False}


# ── What a dangerous write will do, before it is confirmed (BASE-F98) ────────────────────────────────────────────
# A card listing only what the write sends cannot show the expected cash of the drawer's close, nor the invoice a
# rectification issues. A dangerous write may name,
# in its ``ai=``, a read of its own app that tells what it will do (``preview``): run as the person who asks, with
# the data of the write its input takes, before the card.


class SettleIn(Schema):
    id: str = Field(min_length=1)
    reason: str = ""


class SettlePreviewIn(Schema):
    id: str = Field(min_length=1)


class SettlePreviewOut(Schema):
    name: str = Field(title="Owner")
    total_cents: int = Field(json_schema_extra={"money": True})
    expected_balance: int | None = Field(
        description="The cash there should be, in cents; none when it is hidden.", json_schema_extra={"money": True}
    )
    asked_by: str = Field(title="Person")
    note: str = ""


def settle_preview(ctx, data):
    if data.id == "gone":
        raise OperationError("This item is not there any more.", code="demo.item_not_found", status=404)
    return {"name": f"Item {data.id}", "total_cents": 4200, "expected_balance": None, "asked_by": ctx.actor, "note": ""}


# Not the order of the read's answer: the card follows the order the app names them in.
PREVIEW_FIELDS = ["asked_by", "name", "total_cents", "expected_balance", "note"]
SETTLE_PREVIEW = Operation(
    name="demo.item.settle_preview",
    kind="query",
    permission="demo.view",
    input=SettlePreviewIn,
    output=SettlePreviewOut,
    expose_api=False,
    ai={"description": "What settling a demo item would do."},
    fn=settle_preview,
)
SETTLE = Operation(
    name="demo.item.settle",
    kind="command",
    permission="demo.manage",
    input=SettleIn,
    output=SettlePreviewOut,
    expose_api=False,
    ai={
        "description": "Settles a demo item.",
        "risk": "high",
        "preview": {"operation": "demo.item.settle_preview", "fields": PREVIEW_FIELDS},
    },
    fn=lambda ctx, data: settle_preview(ctx, data),
)


@pytest.fixture
def settle(monkeypatch):
    """The write and its preview, registered as an app's would be."""
    monkeypatch.setitem(registry, SETTLE.name, SETTLE)
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    return SETTLE


@HUB_DB
def test_a_dangerous_write_shows_what_its_app_says_it_will_do_read_as_the_person(settle):
    """In the order its app names them, by their names in the person's language, an amount in cents as money; what
    the read hides from this person (none, as a blind count's expected cash) or leaves empty is not there."""
    failure, fields = assistant.cards.preview(ctx(language="es"), settle, {"id": "7", "reason": "cierre"})
    assert failure is None
    assert shown(fields) == [("asked_by", "text", "ana"), ("name", "text", "Item 7"), ("total_cents", "money", 4200)]
    assert (fields[0]["label"], fields[1]["label"]) == ("Persona", "Propietario")
    _, english = assistant.cards.preview(ctx(language="en", actor="eva"), settle, {"id": "7"})
    assert [(field["label"], field["value"]) for field in english if field["name"] == "asked_by"] == [("Person", "eva")]


def test_a_write_without_a_preview_reads_nothing_and_its_card_is_as_before():
    # A write with neither a preview nor a check (``demo.item.delete`` checks its item since hub#1162).
    assert assistant.cards.preview(ctx(), get("demo.item.create"), {"name": "x"}) == (None, None)
    assert set(assistant.cards.card(get("demo.item.delete"), {"id": "x"}, "es")) == {
        "operation", "app", "app_name", "action", "risk", "fields", "count", "confirm_word", "blocked",
    }


@HUB_DB
def test_a_preview_the_person_may_not_read_is_refused_never_read_for_them(settle):
    """The read runs with the person's own session and permissions, as its screen would: never with more."""
    failure, fields = assistant.cards.preview(ctx({"base.view_home", "demo.manage"}), settle, {"id": "7"})
    assert (failure.outcome, failure.code, fields) == ("refused", "permission_denied", None)


@HUB_DB
def test_a_preview_that_fails_says_why_never_an_empty_one(settle):
    failure, fields = assistant.cards.preview(ctx(), settle, {"id": "gone"})
    assert (failure.outcome, failure.code, fields) == ("error", "demo.item_not_found", None)
    assert json.loads(failure.content)["error"]["message"] == "This item is not there any more."


@HUB_DB
def test_a_preview_whose_data_do_not_fit_comes_back_with_the_field(settle):
    failure, fields = assistant.cards.preview(ctx(), settle, {"reason": "sin id"})
    assert (failure.outcome, failure.code, fields) == ("error", "invalid_payload", None)
    assert "id" in json.loads(failure.content)["error"]["fields"]


class CountPreviewOut(Schema):
    expected_balance: int | None = Field(description="The cash there should be, in cents.", json_schema_extra={"money": True})
    difference: int | None = Field(
        description="Counted − expected, in cents (positive = over, negative = short).",
        json_schema_extra={"signed": True, "money": True},
    )


def count_preview(answer: dict, output: type[Schema] = CountPreviewOut) -> Operation:
    return Operation(
        name="demo.item.count_preview",
        kind="query",
        permission="demo.view",
        input=SettlePreviewIn,
        output=output,
        expose_api=False,
        ai={"description": "What counting a demo item would give."},
        fn=lambda ctx, data: answer,
    )


@HUB_DB
@pytest.mark.parametrize("difference", [13790, -490, 0], ids=["over", "short", "even"])
def test_an_amount_its_read_declares_signed_is_marked_so_and_no_other_amount_is(monkeypatch, difference):
    """A cash difference over came as a bare amount
    («€137.90») where Cash register writes «+€137.90». An amount the read's schema declares signed (``"signed": true``)
    is marked so, whatever its value, for the card to write its sign; the expected cash beside it, and the amounts a
    write sends, stay as they were."""
    read = count_preview({"expected_balance": 11210, "difference": difference})
    write = declaring({"operation": read.name, "fields": ["expected_balance", "difference"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.cards.preview(ctx(), write, {"id": "7"})
    assert failure is None
    assert [{key: value for key, value in field.items() if key != "label"} for field in fields] == [
        {"name": "expected_balance", "kind": "money", "value": 11210},
        {"name": "difference", "kind": "money", "value": difference, "signed": True},
    ]
    assert_a_sent_amount_is_in_the_business_currency()


class PricedPreviewOut(Schema):
    """A read whose amounts are in a currency of its own (an invoice's), as Invoicing's previews answer it."""

    note: str = ""
    total_cents: int = Field(json_schema_extra={"money": True})
    difference: int | None = Field(description="Counted − expected, in cents.", json_schema_extra={"signed": True, "money": True})
    currency: str = ""
    currency_decimals: int | None = None


def priced(monkeypatch, answer: dict) -> list[dict]:
    """The preview of a write whose read answers ``answer``: its data without their labels."""
    read = count_preview({"note": "R1", "total_cents": -12100, "difference": 4200, **answer}, PricedPreviewOut)
    write = declaring({"operation": read.name, "fields": ["note", "total_cents", "difference"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.cards.preview(ctx(), write, {"id": "7"})
    assert failure is None
    return [{key: value for key, value in field.items() if key != "label"} for field in fields]


@HUB_DB
@pytest.mark.parametrize(
    ("answer", "money"),
    [
        ({"currency": "EUR", "currency_decimals": 2}, {"currency": "EUR", "decimals": 2}),
        # Its amounts' minor unit, as the read answers it, even where the currency's own says another (ISK: 0).
        ({"currency": "ISK", "currency_decimals": 2}, {"currency": "ISK", "decimals": 2}),
        ({"currency": "JPY"}, {"currency": "JPY", "decimals": 0}),
    ],
    ids=["its currency and decimals", "decimals as it answers them", "decimals of its currency when it answers none"],
)
def test_an_amount_of_a_preview_carries_the_currency_its_read_answers(monkeypatch, answer, money):
    """An invoice issued in EUR, rectified once the
    business had moved to another currency, showed «-100,00» in the new one on the card. An amount of the preview
    carries the currency the read answers (``currency``) with its decimals (``currency_decimals``, else the
    currency's own: no yen with cents), the sign of a difference with it; a datum that is no amount, none; and the
    amounts a write sends stay in the business's (the card's ``money``)."""
    assert priced(monkeypatch, answer) == [
        {"name": "note", "kind": "text", "value": "R1"},
        {"name": "total_cents", "kind": "money", "value": -12100, "money": money},
        {"name": "difference", "kind": "money", "value": 4200, "signed": True, "money": money},
    ]
    assert_a_sent_amount_is_in_the_business_currency()


@HUB_DB
def test_a_preview_whose_read_answers_no_currency_invents_none(monkeypatch):
    """Without a currency in the read's answer (Cash register's close: the drawer is in the business's), its amounts
    carry none and the card paints them in the business's, as before."""
    assert [field.get("money") for field in priced(monkeypatch, {})] == [None, None, None]
    assert [field.get("money") for field in priced(monkeypatch, {"currency": "", "currency_decimals": 2})] == [None] * 3


def preview_errors() -> list:
    from django.core import checks

    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E005"]


def declaring(preview, *, risk="high", input=SettleIn) -> Operation:
    return Operation(
        name="demo.item.settle",
        kind="command",
        permission="demo.manage",
        input=input,
        output=SettlePreviewOut,
        expose_api=False,
        ai={"description": "Settles a demo item.", "risk": risk, "preview": preview},
        fn=lambda ctx, data: data,
    )


class NoIdIn(Schema):
    reason: str = ""


@pytest.mark.parametrize(
    "write, why",
    [
        (declaring({"operation": "demo.item.nothing", "fields": ["name"]}), "no operation demo.item.nothing"),
        (declaring({"operation": "base.business.get", "fields": ["name"]}), "of another app"),
        (declaring({"operation": "demo.item.create", "fields": ["name"]}), "not a read"),
        (declaring({"operation": "demo.item.settle_preview", "fields": ["name", "total"]}), "no field total"),
        (declaring({"operation": "demo.item.settle_preview", "fields": []}), "names no field"),
        (declaring("demo.item.settle_preview"), "operation and fields"),
        (declaring({"operation": "demo.item.settle_preview", "fields": ["name"]}, input=NoIdIn), "takes id"),
        (declaring({"operation": "demo.item.settle_preview", "fields": ["name"]}, risk="normal"), "not dangerous"),
    ],
)
def test_a_preview_is_checked_at_start(monkeypatch, write, why):
    """Like ``ai=`` itself (live's E017): a preview that names no read of its own app, a datum its read does not give,
    data its write does not have, or that a normal write's one-line card would never show, is said at start."""
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    monkeypatch.setitem(registry, write.name, write)
    [error] = preview_errors()
    assert "demo.item.settle" in error.msg and why in error.msg


class SignedNameOut(Schema):
    name: str = Field(title="Owner", json_schema_extra={"signed": True})
    total_cents: int = Field(json_schema_extra={"signed": True, "money": True})
    paid_cents: str = Field(description="What was paid, in cents, as written.", json_schema_extra={"signed": True})
    counted: int = Field(description="Counted − expected, in cents.", json_schema_extra={"signed": True})
    due_cents: int = Field(json_schema_extra={"signed": True})
    written: str = Field(json_schema_extra={"signed": True, "money": True})


def test_a_preview_marks_signed_only_an_amount(monkeypatch):
    """A sign means over or short: only an amount — a whole number its schema marks ``money`` — may be declared
    signed, said at start like the rest. A text is no amount, whether its name says cents or its schema marks it
    ``money`` (the mark alone is not enough: an amount is a whole number), nor a number whose description says cents
    without the mark, nor one whose name does (hub#917:
    a ``…_cents`` without the mark)."""
    read = count_preview({}, SignedNameOut)
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(
        registry,
        SETTLE.name,
        declaring({"operation": read.name, "fields": ["name", "total_cents", "paid_cents", "counted", "due_cents", "written"]}),
    )
    [error] = preview_errors()
    assert "marks name signed, but it is no amount marked money" in error.msg
    assert "marks paid_cents signed, but it is no amount marked money" in error.msg
    assert "marks counted signed, but it is no amount marked money" in error.msg
    assert "marks due_cents signed, but it is no amount marked money" in error.msg
    assert "marks written signed, but it is no amount marked money" in error.msg
    assert "total_cents" not in error.msg


@pytest.mark.parametrize(
    ("prop", "value"),
    [
        ({"type": "string", "signed": True, "money": True}, "Ana"),
        ({"type": "integer", "description": "Counted − expected.", "signed": True, "money": True}, None),
        ({"type": "integer", "description": "Counted − expected.", "signed": "yes", "money": True}, 13790),
    ],
    ids=["a text", "an amount left empty", "not declared with True"],
)
def test_only_an_amount_declared_signed_carries_the_mark(prop, value):
    """The mark is for the card to write a sign on an amount: a datum that is no amount in cents, an amount left empty
    (a difference hidden from this person) or a declaration that is not ``True`` carry none, whatever the schema says."""
    assert "signed" not in shared.field("difference", "Diferencia", prop, {}, value)


def test_the_previews_of_today_are_declared_right(settle):
    assert preview_errors() == []


# ── What a write's app checks before its card (hub#538) ─────────────────────────────────────────────────────────
# A new member with a role the business does not have showed its card, the person said yes, and only then the write
# refused the role. A write may name, in its ``ai=``, a read of its own app that checks its data (``check``): run as
# the person, with the data of the write its input takes, before the card; its refusal is the write's outcome and
# no card is drawn. Nothing of its answer is shown: a normal write's card stays a single line.


class NoteIn(Schema):
    id: str = Field(min_length=1)
    note: str = ""


def checking(check, *, risk="normal", preview=None, input=NoteIn) -> Operation:
    """A write of demo whose ``ai=`` names ``check`` (and, when dangerous, ``preview``)."""
    declared = {"description": "Notes something on a demo item.", "risk": risk, "check": check}
    if preview is not None:
        declared["preview"] = preview
    return Operation(
        name="demo.item.note",
        kind="command",
        permission="demo.manage",
        input=input,
        output=SettlePreviewOut,
        expose_api=False,
        ai=declared,
        fn=lambda ctx, data: data,
    )


@pytest.fixture
def note(monkeypatch):
    """A normal write that checks its item first, registered as an app's would be, with the read it names."""
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    write = checking(SETTLE_PREVIEW.name)
    monkeypatch.setitem(registry, write.name, write)
    return write


@HUB_DB
def test_a_write_whose_check_refuses_its_data_gets_no_card_and_says_why(note):
    failure, fields = assistant.cards.preview(ctx(), note, {"id": "gone", "note": "x"})
    assert (failure.outcome, failure.code, fields) == ("error", "demo.item_not_found", None)
    assert json.loads(failure.content)["error"]["message"] == "This item is not there any more."


@HUB_DB
def test_a_check_that_passes_leaves_a_normal_writes_card_as_it_was(note):
    """Nothing of the check's answer reaches the card: a normal write has no preview."""
    assert assistant.cards.preview(ctx(), note, {"id": "7", "note": "x"}) == (None, None)


class StrictCheckIn(Schema):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)


@HUB_DB
def test_a_check_reads_only_the_data_its_own_input_takes(monkeypatch):
    """The write's other data (its note) never reach its check: a read that refuses data it does not take still lets
    a write whose data it takes reach its card."""
    strict = Operation(**{**vars(SETTLE_PREVIEW), "name": "demo.item.note_check", "input": StrictCheckIn})
    monkeypatch.setitem(registry, strict.name, strict)
    write = checking(strict.name)
    monkeypatch.setitem(registry, write.name, write)
    assert assistant.cards.preview(ctx(), write, {"id": "7", "note": "x"}) == (None, None)
    failure, _ = assistant.cards.preview(ctx(), write, {"id": "gone", "note": "x"})
    assert failure.code == "demo.item_not_found"


@HUB_DB
def test_a_check_the_person_may_not_read_is_refused_never_read_for_them(note):
    failure, fields = assistant.cards.preview(ctx({"base.view_home", "demo.manage"}), note, {"id": "7"})
    assert (failure.outcome, failure.code, fields) == ("refused", "permission_denied", None)


@HUB_DB
def test_a_dangerous_write_is_checked_before_its_preview_is_read(monkeypatch):
    """The check refuses first: the preview is never read for data the write refuses."""
    read: list[str] = []

    def counted(ctx, data):
        read.append(data.id)
        return settle_preview(ctx, data)

    previewed = Operation(**{**vars(SETTLE_PREVIEW), "name": "demo.item.note_preview", "fn": counted})
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    monkeypatch.setitem(registry, previewed.name, previewed)
    write = checking(SETTLE_PREVIEW.name, risk="high", preview={"operation": previewed.name, "fields": ["name"]})
    monkeypatch.setitem(registry, write.name, write)
    failure, _ = assistant.cards.preview(ctx(), write, {"id": "gone"})
    assert (failure.code, read) == ("demo.item_not_found", [])
    failure, fields = assistant.cards.preview(ctx(), write, {"id": "7"})
    assert (failure, shown(fields), read) == (None, [("name", "text", "Item 7")], ["7"])


def check_errors() -> list:
    from django.core import checks

    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E012"]


class NoItemIn(Schema):
    note: str = ""


@pytest.mark.parametrize(
    "write, why",
    [
        (checking("demo.item.nothing"), "names no operation demo.item.nothing"),
        (checking("base.business.get"), "of another app"),
        (checking("demo.item.create"), "not a read"),
        (checking({"operation": "demo.item.settle_preview"}), "is not the name of a read"),
        (checking("demo.item.settle_preview", input=NoItemIn), "the write never takes id"),
    ],
)
def test_a_check_is_checked_at_start(monkeypatch, write, why):
    """Like a preview (base.E005): a check that names no read of its own app, or reads data its write does not
    have, is said at start."""
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    monkeypatch.setitem(registry, write.name, write)
    [error] = check_errors()
    assert "demo.item.note" in error.msg and why in error.msg


def test_the_checks_of_today_are_declared_right(note):
    assert check_errors() == []
