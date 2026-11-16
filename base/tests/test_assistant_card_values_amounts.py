"""How the card of a write says an amount and its currency, and the marks every app gives them."""

import dataclasses
import re

import pytest
from django.core import checks
from live import assistant as shared
from live.errors import NotFound
from live.operations import Operation, registry
from ninja import Field, Schema

from base import assistant
from base.models import Hub
from base.tests.card_values import ADMIN, VisitIn, ctx, values, writes


# ── An amount, known by the mark of its schema ────────────────────────────────────────────────────────────────────────

#: The mark of an amount: a whole number in the minor unit of its currency (``json_schema_extra={"money": True}``).
MONEY = {"money": True}


class PricedLineIn(Schema):
    text: str
    unit_price: int = Field(description="The price of one unit, in minor units of the cart's currency.", json_schema_extra=MONEY)


class PricedIn(Schema):
    # The words of hub#361 and hub#359: neither says «in cents».
    price: int = Field(description="The price, in minor units of the business's currency.", json_schema_extra=MONEY)
    hourly_rate: int | None = Field(None, description="Hourly rate in whole cents.", json_schema_extra=MONEY)
    quantity: int = Field(1, description="How many units.")
    line: PricedLineIn | None = None
    lines: list[PricedLineIn] = []


def priced(input: type[Schema] = PricedIn) -> Operation:
    return Operation(
        name="demo.item.priced",
        kind="command",
        permission="demo.manage",
        input=input,
        output=input,
        expose_api=False,
        ai={"description": "A write with amounts."},
        fn=lambda ctx, data: data,
    )


PRICED_ARGUMENTS = {
    "price": 1500,
    "hourly_rate": 1250,
    "quantity": 2,
    "line": {"text": "Café", "unit_price": 150},
    "lines": [{"text": "Té", "unit_price": 1200}],
}


def amount(value: int, money: dict | None = None) -> dict:
    """An amount inside an object or a list, as the card sends it for its screen to write as one on top."""
    return {"kind": "money", "value": value, **({"money": money} if money else {})}


USD = {"currency": "USD", "decimals": 2}


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "country"), [("es", "ES"), ("en", "ES"), ("es", "PL")], ids=["es", "en", "a business in zlotys"])
def test_an_amount_its_schema_marks_is_money_whatever_its_words_at_any_depth(language, country):
    """hub#361 and hub#359: a price «in minor units…» and a rate «in whole cents» reached the card as a bare figure
    («Precio: 1500»): the card knew an amount only by the words «in cents». Now by its schema's mark, at any depth, as
    money the screen writes in the business's currency, the same inside an object or a list as on top (the server
    never words it: «1,50 PLN» beside «15,00 zł»). A whole number that is no amount stays as sent."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": country})
    card = assistant.cards.card(priced(), PRICED_ARGUMENTS, language, ctx=ctx(language=language))
    shown = {field["name"]: (field["kind"], field["value"]) for field in card["fields"]}
    assert shown == {
        "price": ("money", 1500),
        "hourly_rate": ("money", 1250),
        "quantity": ("text", 2),
        "line": ("object", {"text": "Café", "unit_price": amount(150)}),
        "lines": ("list", [{"text": "Té", "unit_price": amount(1200)}]),
    }


class WordsOnlyIn(Schema):
    price: int = Field(description="Price in cents.")
    rate: int = Field(description="Hourly rate in whole cents.")


def test_words_alone_make_no_amount_its_mark_does():
    """The words of a description are for the model, and rewriting them changes nothing of the card: the mark says an
    amount. Every amount the assistant shows or fills carries its mark (the ratchet below)."""
    card = assistant.cards.card(priced(WordsOnlyIn), {"price": 1500, "rate": 1250}, "es")
    assert [(field["name"], field["kind"]) for field in card["fields"]] == [("price", "text"), ("rate", "text")]


class CentsLineIn(Schema):
    text: str
    unit_cents: int


class NamedCentsIn(Schema):
    total_cents: int
    line: CentsLineIn | None = None
    lines: list[CentsLineIn] = []


@pytest.mark.django_db
def test_a_name_in_cents_alone_makes_no_amount_its_mark_does():
    """hub#917: a whole number named ``…_cents`` was money by its name while its schema carried no mark, so a new
    datum named so that is no amount would reach the card as money in the business's currency. Only the mark says an
    amount, on top and inside an object or a list: the rest stays as sent."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    arguments = {"total_cents": 1500, "line": {"text": "Café", "unit_cents": 150}, "lines": [{"text": "Té", "unit_cents": 1200}]}
    card = assistant.cards.card(priced(NamedCentsIn), arguments, "es", ctx=ctx(language="es"))
    shown = {field["name"]: (field["kind"], field["value"]) for field in card["fields"]}
    assert shown == {
        "total_cents": ("text", 1500),
        "line": ("object", {"text": "Café", "unit_cents": 150}),
        "lines": ("list", [{"text": "Té", "unit_cents": 1200}]),
    }


class DueOut(Schema):
    due: int = Field(description="What is left to pay.", json_schema_extra=MONEY)
    note: str = ""


class InvoicedPreviewOut(Schema):
    totals: DueOut
    currency: str = ""


@pytest.mark.django_db
def test_an_amount_inside_a_datum_of_a_preview_is_said_in_the_currency_its_read_answers(monkeypatch):
    """As the amounts on top of «What will happen» (BASE-F98): an invoice keeps the currency it was issued in."""
    from base.tests.test_assistant import count_preview, declaring

    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    read = count_preview({"totals": {"due": 1200, "note": "R1"}, "currency": "USD"}, output=InvoicedPreviewOut)
    write = declaring({"operation": read.name, "fields": ["totals"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.cards.preview(ctx({*ADMIN, "demo.view", "demo.manage"}, language="en"), write, {"id": "7"})
    assert failure is None
    assert [(field["name"], field["kind"], field["value"]) for field in fields] == [
        ("totals", "object", {"due": amount(1200, USD), "note": "R1"})
    ]


def test_the_model_is_told_an_amount_by_its_mark_whatever_its_description_says():
    """The tool the model fills carries the mark of each amount, at any depth, and its instructions say what the mark
    means: the minor unit of the business's currency. Words like «in cents» are not what tells it."""
    parameters = shared.tool_spec(priced())["parameters"]
    defs = parameters["$defs"]
    assert shared.resolved(parameters["properties"]["price"], defs)["money"] is True
    assert shared.resolved(parameters["properties"]["hourly_rate"], defs)["money"] is True
    assert defs["PricedLineIn"]["properties"]["unit_price"]["money"] is True
    assert "money" not in shared.resolved(parameters["properties"]["quantity"], defs)
    text = assistant.prompt.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={})
    assert '`"money": true`' in text and "17.00 EUR → 1700" in text
    assert "«in cents»" not in text


# ── The currency a write names: its amounts are in it ────────────────────────────────────────────────────────────────

#: The mark of the datum that names the currency of the amounts beside it (``json_schema_extra={"currency": True}``).
NAMES_THE_CURRENCY = {"currency": True}


class PaidIn(Schema):
    amount: int = Field(description="The amount in minor units of the currency.", json_schema_extra=MONEY)
    currency: str | None = Field(
        None, description="ISO 4217 code; without it, the business's currency.", json_schema_extra=NAMES_THE_CURRENCY
    )
    line: PricedLineIn | None = None


def paid(arguments: dict, language: str = "es") -> dict:
    """The card of a payment of 15.00 with a line of 1.50 and ``arguments``, read as the person: its data by name."""
    card = assistant.cards.card(
        priced(PaidIn), {"amount": 1500, "line": {"text": "Café", "unit_price": 150}, **arguments}, language, ctx=ctx(language=language)
    )
    return {field["name"]: {key: value for key, value in field.items() if key != "label"} for field in card["fields"]}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("sent", "money"),
    [
        ("USD", USD),
        ("JPY", {"currency": "JPY", "decimals": 0}),
        (" usd ", USD),
    ],
    ids=["dollars", "yen, without decimals", "as the write takes it"],
)
def test_an_amount_of_a_write_that_names_its_currency_is_in_that_currency(sent, money):
    """A payment in dollars from a business in euros said «15,00 €»: the card painted every amount of a write in the
    business's currency. As Stripe, Square or Shopify show an amount, in the currency of its operation, with that
    currency's decimals (none in yen): the one the datum its schema marks ``currency`` names, inside an object too."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    shown = paid({"currency": sent})
    assert shown["amount"] == {"name": "amount", "kind": "money", "value": 1500, "money": money}
    assert shown["line"]["value"] == {"text": "Café", "unit_price": amount(150, money)}


@pytest.mark.django_db
@pytest.mark.parametrize("arguments", [{}, {"currency": ""}, {"currency": None}], ids=["none", "empty", "null"])
def test_an_amount_of_a_write_that_names_no_currency_is_in_the_businesss(arguments):
    """Without one, the write takes the business's currency, and so does its card: no currency of its own."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "PL"})
    shown = paid(arguments)
    assert shown["amount"] == {"name": "amount", "kind": "money", "value": 1500}
    assert shown["line"]["value"] == {"text": "Café", "unit_price": amount(150)}


@pytest.mark.django_db
@pytest.mark.parametrize("sent", ["XYZ", "EURO", "€", "12", 12], ids=["XYZ", "EURO", "euro sign", "12 as text", "12 as a number"])
def test_an_amount_in_a_currency_that_is_none_is_shown_as_sent_never_in_another(sent):
    """A code that is no ISO 4217 currency — or no text at all, a number — is refused by the write («That is not a
    currency code»): its card makes no currency up, neither the business's nor another; its amounts go as sent, as the
    code itself."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    shown = paid({"currency": sent})
    assert shown["amount"] == {"name": "amount", "kind": "text", "value": 1500}
    assert shown["currency"]["value"] == sent
    assert shown["line"]["value"] == {"text": "Café", "unit_price": 150}


class PaidLineIn(Schema):
    text: str
    unit_price: int = Field(json_schema_extra=MONEY)
    currency: str = Field("", json_schema_extra=NAMES_THE_CURRENCY)


class PaidLinesIn(Schema):
    lines: list[PaidLineIn] = []
    line: PaidLineIn | None = None


@pytest.mark.django_db
def test_inside_an_object_the_currency_it_names_is_the_one_of_its_amounts():
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    line = {"text": "Café", "unit_price": 150, "currency": "USD"}
    card = assistant.cards.card(priced(PaidLinesIn), {"line": line, "lines": [line, {**line, "currency": ""}]}, "en", ctx=ctx(language="en"))
    assert values(card) == {
        "line": {"text": "Café", "unit_price": amount(150, USD), "currency": "USD"},
        "lines": [{"text": "Café", "unit_price": amount(150, USD), "currency": "USD"}, {"text": "Café", "unit_price": amount(150), "currency": ""}],
    }


def test_the_model_is_told_an_amount_is_in_the_currency_its_write_names():
    """The minor unit of its operation's currency: 1500 is 15.00 dollars in a payment in dollars, ¥1,500 in yen."""
    assert shared.resolved(shared.tool_spec(priced(PaidIn))["parameters"]["properties"]["currency"], {})["currency"] is True
    text = assistant.prompt.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={})
    assert '`"currency": true`' in text


# ── The currency of the record a write is on: a line of a cart in dollars, a price of a list in yen ──────────────────

#: The ledgers of the test, by id: the currency each one answers.
LEDGERS = {"L-USD": "USD", "L-JPY": "JPY", "L-BAD": "DOLLARS"}
JPY = {"currency": "JPY", "decimals": 0}


class LedgerIn(Schema):
    id: str | None = None
    name: str | None = None


class LedgerOut(Schema):
    name: str
    code: str


def ledger_of(read: list):
    def ledger(ctx, data):
        read.append(data.model_dump())
        key = data.id or {"Dólares": "L-USD"}.get(data.name or "", "")
        if key not in LEDGERS:
            raise NotFound("There is no such ledger.")
        return {"name": key, "code": LEDGERS[key]}

    return Operation(
        name="demo.item.ledger",
        kind="query",
        permission="demo.view",
        input=LedgerIn,
        output=LedgerOut,
        expose_api=False,
        ai={"description": "A ledger by its id or its name."},
        fn=ledger,
    )


def in_ledger(by: str) -> dict:
    """The mark of a datum that names the record whose currency is the one of the amounts beside it."""
    return {"currency": {"read": "demo.item.ledger", "by": by, "code": "code"}}


class LedgerEntryIn(Schema):
    ledger_id: str | None = Field(None, json_schema_extra=in_ledger("id"))
    ledger: str | None = Field(None, json_schema_extra=in_ledger("name"))
    price: int | None = Field(None, description="In minor units of the ledger's currency.", json_schema_extra=MONEY)
    line: PricedLineIn | None = None


@pytest.fixture
def ledger_reads(monkeypatch) -> list:
    """The ledger's read registered as an app's would be: what it was asked, in order."""
    read: list = []
    op = ledger_of(read)
    monkeypatch.setitem(registry, op.name, op)
    return read


ENTRY = {"price": 1500, "line": {"text": "Café", "unit_price": 150}}
WRITER = {*ADMIN, "demo.view", "demo.manage"}


def entered(arguments: dict, permissions=WRITER, *, person: bool = True) -> dict:
    card = assistant.cards.card(priced(LedgerEntryIn), arguments, "es", ctx=ctx(permissions) if person else None)
    return {field["name"]: {key: value for key, value in field.items() if key != "label"} for field in card["fields"]}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("named", "money"),
    [({"ledger_id": "L-USD"}, USD), ({"ledger": "Dólares"}, USD), ({"ledger_id": "L-JPY"}, JPY)],
    ids=["by its id", "by its name", "yen, without decimals"],
)
def test_an_amount_of_a_write_on_a_record_is_in_that_records_currency(ledger_reads, named, money):
    """A line of a cart in dollars said «12,50 €»: the write names the record, not the currency. The datum that names
    it carries the read of its app that answers its currency (``currency``: read, by, code); the card runs it as the
    person, as it reads a record's name, and says every amount beside it in that currency, inside an object too."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    shown = entered({**ENTRY, **named})
    assert shown["price"] == {"name": "price", "kind": "money", "value": 1500, "money": money}
    assert shown["line"]["value"] == {"text": "Café", "unit_price": amount(150, money)}
    assert len(ledger_reads) == 1


@pytest.mark.django_db
def test_an_amount_only_inside_an_object_is_also_in_the_records_currency(ledger_reads):
    """A write whose only amount is a line's price: the record is read for it all the same."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    shown = entered({"ledger_id": "L-USD", "line": {"text": "Café", "unit_price": 150}})
    assert shown["line"]["value"] == {"text": "Café", "unit_price": amount(150, USD)}
    assert len(ledger_reads) == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("named", "permissions"),
    [({"ledger_id": "L-GONE"}, WRITER), ({"ledger_id": "L-USD"}, {*ADMIN, "demo.manage"}), ({"ledger_id": "L-BAD"}, WRITER)],
    ids=["not there", "not theirs to read", "answers no currency"],
)
def test_an_amount_on_a_record_whose_currency_cannot_be_read_is_shown_as_sent(ledger_reads, named, permissions):
    """As a currency that is none: the card makes none up, neither the business's nor another; the write decides."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    shown = entered({**ENTRY, **named}, permissions)
    assert shown["price"] == {"name": "price", "kind": "text", "value": 1500}
    assert shown["line"]["value"] == {"text": "Café", "unit_price": 150}


def test_without_the_person_a_records_currency_is_never_read(ledger_reads):
    """An automation's card reads nothing for somebody else: its amounts go as sent."""
    shown = entered({**ENTRY, "ledger_id": "L-USD"}, person=False)
    assert shown["price"] == {"name": "price", "kind": "text", "value": 1500}
    assert ledger_reads == []


@pytest.mark.django_db
def test_a_record_is_read_only_for_its_amounts_and_one_not_named_leaves_the_businesss(ledger_reads):
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    assert entered({"ledger_id": "L-USD"}) == {"ledger_id": {"name": "ledger_id", "kind": "text", "value": "L-USD"}}
    assert ledger_reads == []
    assert entered(ENTRY)["price"] == {"name": "price", "kind": "money", "value": 1500}
    assert ledger_reads == []


def test_the_model_is_told_an_amount_on_a_record_is_in_that_records_currency():
    """A line of a cart in dollars, a price of a list in yen: its tool carries the mark on the datum that names the
    record, and its instructions say the amount beside it is in the minor unit of that record's currency."""
    parameters = shared.tool_spec(priced(LedgerEntryIn))["parameters"]
    assert shared.resolved(parameters["properties"]["ledger_id"], parameters.get("$defs", {}))["currency"] == {
        "read": "demo.item.ledger",
        "by": "id",
        "code": "code",
    }
    text = assistant.prompt.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={})
    assert '`"currency": {"read": …}`' in text and '`"currency": true`' in text


def currency_errors() -> list:
    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E011"]


def test_the_currency_marks_of_every_app_are_sound():
    assert currency_errors() == []


def entering(mark: object) -> Operation:
    class MarkedEntryIn(Schema):
        ledger_id: str | None = Field(None, json_schema_extra={"currency": mark})
        price: int = Field(json_schema_extra=MONEY)

    return dataclasses.replace(priced(MarkedEntryIn), name="demo.item.enter")


@pytest.mark.parametrize(
    ("write", "why"),
    [
        (entering("demo.item.ledger"), "is not true nor a read, by and code"),
        (entering({"read": "demo.item.ledger", "by": "id"}), "is not true nor a read, by and code"),
        (entering(False), "is not true nor a read, by and code"),
        (entering({"read": "demo.item.nothing", "by": "id", "code": "code"}), "names no operation demo.item.nothing"),
        (entering({"read": "demo.item.create", "by": "id", "code": "code"}), "not a read"),
        (entering({"read": "demo.item.ledger", "by": "who", "code": "code"}), "takes no who"),
        (entering({"read": "demo.item.ledger", "by": "id", "code": "currency"}), "gives no currency"),
        (entering({"read": "cart_checkout.cart.get", "by": "cart_id", "code": "currency"}), "which demo does not require"),
    ],
)
def test_a_currency_mark_is_checked_at_start(monkeypatch, ledger_reads, write, why):
    """Like ``refers`` (base.E009): a mark that names no read of its app (or of one it requires), that does not take the
    datum or answers no currency is said at start, never found out on a card."""
    monkeypatch.setitem(registry, write.name, write)
    [error] = currency_errors()
    assert "demo.item.enter" in error.msg and why in error.msg


# ── The ratchet: amounts nobody marks, by app ─────────────────────────────────────────────────────────────────────────

#: How an amount says itself in this repo's schemas: a whole number named ``…_cents``, or whose description speaks of
#: cents or of the minor unit (``in cents``, ``in whole cents``, ``in minor units``, «céntimos»). Not a percentage
#: («Percent off in basis points»), a count, nor a text whose name says cents.
AMOUNT_WORDS = re.compile(r"\bcents?\b|\bminor units?\b|\bcéntimos?\b", re.IGNORECASE)

#: The amounts the assistant shows or fills that no ``money`` mark declares, by app: the card paints them as a bare
#: figure and the model is not told their unit. Only ever lower: an app that marks its own lowers its number here, and
#: none comes in.
UNMARKED_AMOUNTS: dict[str, int] = {}


def is_marked_amount(prop: dict) -> bool:
    return prop.get("money") is True


def looks_like_an_amount(name: str, prop: dict) -> bool:
    return prop.get("type") == "integer" and (
        name.endswith("_cents") or bool(AMOUNT_WORDS.search(str(prop.get("description", ""))))
    )


def data_of(schema: dict, names: list[str] | None = None) -> list[tuple[str, str, dict]]:
    """Each datum of ``schema`` (only ``names`` on top, when given), at any depth: its name, its path and its schema."""
    defs = schema.get("$defs", {})
    found: list[tuple[str, str, dict]] = []

    def walk(name: str, prop: dict, path: str, depth: int) -> None:
        prop = shared.resolved(prop, defs)
        if depth > 8:
            return
        found.append((name, path, prop))
        if isinstance(prop.get("items"), dict):
            walk(name, prop["items"], f"{path}[]", depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner, inner_prop, f"{path}.{inner}", depth + 1)

    for name, prop in schema.get("properties", {}).items():
        if names is None or name in names:
            walk(name, prop, name, 0)
    return found


def assistant_data(op: Operation) -> list[tuple[str, str, dict]]:
    """What the assistant shows or fills of the tool ``op``: its input (the model's parameters, a write's card) and,
    for a write with a preview, the data of its read's answer the card shows («What will happen»)."""
    found = data_of(op.input.model_json_schema())
    declared = shared.preview_of(op)
    read = registry.get(declared["operation"]) if isinstance(declared, dict) else None
    if read is not None:
        found += [(name, f"preview:{path}", prop) for name, path, prop in data_of(read.output.model_json_schema(), declared["fields"])]
    return found


def tools() -> list[Operation]:
    return [op for _, op in sorted(registry.items()) if assistant.tools.is_tool(op)]


def unmarked_amounts(op: Operation) -> list[str]:
    """``op``'s data that look like an amount (``looks_like_an_amount``) and no mark declares so, at any depth."""
    return [path for name, path, prop in assistant_data(op) if looks_like_an_amount(name, prop) and not is_marked_amount(prop)]


def amounts_by_app(operations) -> dict[str, int]:
    counted: dict[str, int] = {}
    for op in operations:
        if found := unmarked_amounts(op):
            counted[op.app_label] = counted.get(op.app_label, 0) + len(found)
    return dict(sorted(counted.items()))


def test_every_amount_the_assistant_shows_or_fills_is_marked_but_the_known_ones():
    """A new amount without its mark — or one whose mark is lost while its words say cents — fails here; an app that
    marks its own lowers its number."""
    assert amounts_by_app(tools()) == UNMARKED_AMOUNTS


class UnmarkedPriceLineIn(Schema):
    text: str
    unit_price: int = Field(description="The price of one unit, in minor units.")


class UnmarkedAmountsIn(Schema):
    price: int = Field(description="The price, in minor units of the business's currency.")
    hourly_rate: int | None = Field(None, description="Hourly rate in whole cents.")
    total_cents: int = 0
    lines: list[UnmarkedPriceLineIn] = []
    marked: int = Field(0, description="Price in cents.", json_schema_extra=MONEY)
    discount_percent_bp: int = Field(0, description="Percent off in basis points (1050 = 10.50 %).")
    quantity: int = Field(1, description="How many units.")
    note_cents: str = Field("", description="A note, in cents as written.")


def test_the_ratchet_counts_an_amount_nobody_marks_and_nothing_else():
    """The words of hub#361 («in minor units») and hub#359 («in whole cents») give an amount away, a name in
    ``_cents`` too, at any depth; a marked one, a percentage, a count or a text are not counted."""
    op = priced(UnmarkedAmountsIn)
    assert unmarked_amounts(op) == ["price", "hourly_rate", "total_cents", "lines[].unit_price"]
    assert amounts_by_app([op, op]) == {"demo": 8}


def test_no_amount_the_card_painted_as_money_stops_being_one():
    """What the card painted as money by its words before (a whole number named ``_cents`` or described «in cents»)
    carries the mark now, every one of them: nothing that was money stops being so."""
    def by_words(name: str, prop: dict) -> bool:
        return prop.get("type") == "integer" and (name.endswith("_cents") or "in cents" in str(prop.get("description", "")).lower())

    painted = {(op.name, path) for op in tools() for name, path, prop in assistant_data(op) if by_words(name, prop)}
    marked = {(op.name, path) for op in tools() for _, path, prop in assistant_data(op) if is_marked_amount(prop)}
    assert len(painted) > 50
    assert sorted(painted - marked) == []


def misplaced_money(op: Operation) -> list[str]:
    """``op``'s data marked ``money`` that are no whole number, at any depth, in what it takes and what it answers."""
    return [
        f"{side}:{path}"
        for side, schema in (("in", op.input.model_json_schema()), ("out", op.output.model_json_schema()))
        for _, path, prop in data_of(schema)
        if is_marked_amount(prop) and prop.get("type") != "integer"
    ]


class MisplacedMoneyIn(Schema):
    name: str = Field(json_schema_extra=MONEY)
    ratio: float = Field(json_schema_extra=MONEY)
    line: PricedLineIn = Field(json_schema_extra=MONEY)
    price: int = Field(json_schema_extra=MONEY)


def test_an_amount_is_marked_only_on_a_whole_number():
    """An amount goes in the minor unit of its currency, a whole number: the mark on a text, a fraction or an object
    would paint as money what is none. Every operation of every app, at any depth."""
    assert misplaced_money(priced(MisplacedMoneyIn)) == ["in:name", "in:ratio", "in:line", "out:name", "out:ratio", "out:line"]
    assert [f"{name}:{path}" for name, op in sorted(registry.items()) for path in misplaced_money(op)] == []


# ── The ratchet: currencies of a write nobody marks, by app ───────────────────────────────────────────────────────────

#: How a datum names a currency in this repo's schemas: ``currency`` (Payments, Carts, Price lists), ``…_currency``, or
#: a text whose description says ISO 4217.
CURRENCY_NAME = re.compile(r"^(?:\w+_)?currency$")

#: The data of the assistant's writes that name the currency of an amount beside them (in the same object, or below
#: it) and no ``currency`` mark declares, by app: the card paints that amount in the business's currency. Only ever
#: lower, as above.
UNMARKED_CURRENCIES: dict[str, int] = {}


def names_a_currency(name: str, prop: dict) -> bool:
    return prop.get("type") == "string" and (
        bool(CURRENCY_NAME.match(name)) or "ISO 4217" in str(prop.get("description", ""))
    )


def unmarked_currencies(op: Operation) -> list[str]:
    """``op``'s data that name a currency (``names_a_currency``) beside an amount its schema marks, at any depth, and no
    mark declares so."""
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})
    found: list[str] = []

    def priced(prop: dict, depth: int) -> bool:
        prop = shared.resolved(prop, defs)
        if depth > 8:
            return False
        if is_marked_amount(prop):
            return True
        inner = [*prop.get("properties", {}).values(), *([prop["items"]] if isinstance(prop.get("items"), dict) else [])]
        return any(priced(each, depth + 1) for each in inner)

    def walk(prop: dict, path: str, depth: int) -> None:
        prop = shared.resolved(prop, defs)
        if depth > 8:
            return
        props = prop.get("properties", {})
        if priced(prop, depth):
            found.extend(
                f"{path}.{name}" if path else name
                for name, inner in props.items()
                if names_a_currency(name, shared.resolved(inner, defs))
                and shared.resolved(inner, defs).get("currency") is not True
            )
        if isinstance(prop.get("items"), dict):
            walk(prop["items"], f"{path}[]", depth + 1)
        for name, inner in props.items():
            walk(inner, f"{path}.{name}" if path else name, depth + 1)

    walk(schema, "", 0)
    return found


def test_every_currency_a_write_names_beside_its_amount_is_marked_but_the_known_ones():
    counted: dict[str, int] = {}
    for op in writes():
        if found := unmarked_currencies(op):
            counted[op.app_label] = counted.get(op.app_label, 0) + len(found)
    assert dict(sorted(counted.items())) == UNMARKED_CURRENCIES


class UnmarkedCurrencyLineIn(Schema):
    unit_price: int = Field(json_schema_extra=MONEY)
    price_currency: str = ""


class UnmarkedCurrenciesIn(Schema):
    amount: int = Field(json_schema_extra=MONEY)
    currency: str | None = None
    code: str = Field("", description="ISO 4217 code of the payment.")
    marked: str = Field("", json_schema_extra=NAMES_THE_CURRENCY)
    lines: list[UnmarkedCurrencyLineIn] = []
    other: VisitIn | None = None


class UnpricedCurrencyIn(Schema):
    currency: str = ""
    name: str = ""


def test_the_ratchet_counts_a_currency_beside_an_amount_nobody_marks_and_nothing_else():
    """A currency beside an amount, by its name or its description, at any depth; a marked one, or one with no amount
    beside it (a cart created in dollars, a price list), are not counted."""
    assert unmarked_currencies(priced(UnmarkedCurrenciesIn)) == ["currency", "code", "lines[].price_currency"]
    assert unmarked_currencies(priced(UnpricedCurrencyIn)) == []


def misplaced_currency_marks(op: Operation) -> list[str]:
    return [
        f"{side}:{path}"
        for side, schema in (("in", op.input.model_json_schema()), ("out", op.output.model_json_schema()))
        for _, path, prop in data_of(schema)
        if prop.get("currency") is True and prop.get("type") != "string"
    ]


class MisplacedCurrencyIn(Schema):
    amount: int = Field(json_schema_extra={**MONEY, **NAMES_THE_CURRENCY})
    line: PricedLineIn = Field(json_schema_extra=NAMES_THE_CURRENCY)
    currency: str = Field("", json_schema_extra=NAMES_THE_CURRENCY)


def test_a_currency_is_marked_only_on_a_text():
    """The mark names a code (ISO 4217): on a number or an object it would say a currency that is none."""
    assert misplaced_currency_marks(priced(MisplacedCurrencyIn)) == ["in:amount", "in:line", "out:amount", "out:line"]
    assert [f"{name}:{path}" for name, op in sorted(registry.items()) for path in misplaced_currency_marks(op)] == []


# ── The ratchet: amounts on a record in a currency of its own nobody marks, by app ──────────────────────────────────

#: How an amount says it is in the currency of a record and not the business's: «in minor units of the cart's
#: currency», «in cents of the list's currency».
RECORD_CURRENCY = re.compile(r"\b(?!business's\b)\w+'s currency\b")

#: The amounts of the assistant's writes in the currency of a record that no ``currency`` mark beside them (or above
#: them) says how to read, by app: the card paints them in the business's currency. Only ever lower.
UNPRICED_RECORD_AMOUNTS: dict[str, int] = {}


def unpriced_record_amounts(op: Operation) -> list[str]:
    """``op``'s amounts whose description says they are in a record's currency and that no datum marked ``currency``
    in their object, or in one above it, says how to read, at any depth."""
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})
    found: list[str] = []

    def walk(prop: dict, path: str, priced: bool, depth: int) -> None:
        prop = shared.resolved(prop, defs)
        if depth > 8:
            return
        props = prop.get("properties", {})
        priced = priced or any(shared.resolved(inner, defs).get("currency") for inner in props.values())
        for name, inner in props.items():
            inner = shared.resolved(inner, defs)
            here = f"{path}.{name}" if path else name
            if is_marked_amount(inner) and RECORD_CURRENCY.search(str(inner.get("description", ""))) and not priced:
                found.append(here)
            walk(inner, here, priced, depth + 1)
        if isinstance(prop.get("items"), dict):
            walk(prop["items"], f"{path}[]", priced, depth + 1)

    walk(schema, "", False, 0)
    return found


def test_every_amount_on_a_record_in_a_currency_of_its_own_says_how_to_read_it_but_the_known_ones():
    counted: dict[str, int] = {}
    for op in writes():
        if found := unpriced_record_amounts(op):
            counted[op.app_label] = counted.get(op.app_label, 0) + len(found)
    assert dict(sorted(counted.items())) == UNPRICED_RECORD_AMOUNTS


class CartLineIn(Schema):
    unit_price: int = Field(description="The price of one unit in minor units of the cart's currency.", json_schema_extra=MONEY)
    fee: int = Field(0, description="In minor units of the business's currency.", json_schema_extra=MONEY)


class UnpricedEntriesIn(Schema):
    price: int = Field(description="Price in cents of the list's currency (12.50 = 1250).", json_schema_extra=MONEY)
    lines: list[CartLineIn] = []
    entry: LedgerEntryIn | None = None


class PricedEntriesIn(Schema):
    ledger_id: str | None = Field(None, json_schema_extra=in_ledger("id"))
    lines: list[CartLineIn] = []


def test_the_ratchet_counts_an_amount_on_a_record_nobody_says_how_to_read_and_nothing_else():
    """An amount in the cart's or the list's currency without the mark is counted, inside a list too; one in the
    business's, or with a ``currency`` mark in its object or above it, is not."""
    assert unpriced_record_amounts(priced(UnpricedEntriesIn)) == ["price", "lines[].unit_price"]
    assert unpriced_record_amounts(priced(PricedEntriesIn)) == []
