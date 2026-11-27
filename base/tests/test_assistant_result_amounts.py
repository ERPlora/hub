"""Every amount a tool answers carries its mark: the model reads an amount in its currency only by that mark.

A tool's result reaches the model as the screens write it (``live.assistant.run_tool`` with ``money``), but the model
never sees the result's schema: an amount without the mark goes in cents, and the model repeats the figure as it
reads it (360 told as «360,00 €»).
"""

import json

import pytest
from live.context import OperationContext
from live.operations import Operation
from ninja import Field, Schema

from base import assistant
from base.models import Hub
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.test_assistant_card_values_amounts import (
    MONEY,
    data_of,
    is_marked_amount,
    looks_like_an_amount,
    priced,
    tools,
)

__all__ = ["in_business_a"]


def unmarked_answers(op: Operation) -> list[str]:
    """The data of ``op``'s answer that look like an amount (``looks_like_an_amount``) and no mark declares so, at any
    depth."""
    return [
        path
        for name, path, prop in data_of(op.output.model_json_schema())
        if looks_like_an_amount(name, prop) and not is_marked_amount(prop)
    ]


class LineOut(Schema):
    unit_price: int = Field(description="Its price, in cents.")
    quantity: int


class AnsweredOut(Schema):
    revenue: int = Field(description="What they spent, in cents.")
    total_cents: int
    base_amount: int
    total: int = Field(description="How many rows match.")
    marked: int = Field(description="Price in cents.", json_schema_extra=MONEY)
    currency_decimals: int = Field(description="The decimals of its currency: its amounts' minor unit.")
    lines: list[LineOut]


def test_the_ratchet_counts_an_answered_amount_nobody_marks_and_nothing_else():
    assert unmarked_answers(priced(AnsweredOut)) == ["revenue", "total_cents", "base_amount", "lines[].unit_price"]


def test_every_amount_a_tool_answers_is_marked():
    assert {op.name: found for op in tools() if (found := unmarked_answers(op))} == {}


def test_every_amount_a_tool_answers_would_be_missed_here_without_its_mark():
    """The ratchet knows an amount only by its name or its description: a marked one that neither says so («Sales in
    cash», «Its total») could lose its mark, and reach the model in cents again, with nothing failing."""
    unseen = {
        f"{op.name}:{path}"
        for op in tools()
        for name, path, prop in data_of(op.output.model_json_schema())
        if is_marked_amount(prop) and not looks_like_an_amount(name, prop)
    }
    assert unseen == set()


class PriceListOut(Schema):
    currency: str
    price: int = Field(json_schema_extra=MONEY)


class FiguresOut(Schema):
    revenue: int = Field(json_schema_extra=MONEY)
    price_list: PriceListOut


def told(language: str = "es") -> dict:
    """What the model reads, asked in ``language``, of a read that answers an amount of the business and one of a price
    list in yen."""
    figures = Operation(
        name="demo.item.figures",
        kind="query",
        permission="demo.view",
        input=Schema,
        output=FiguresOut,
        expose_api=False,
        ai={"description": "A read with amounts."},
        fn=lambda ctx, data: {"revenue": 360, "price_list": {"currency": "JPY", "price": 950}},
    )
    ctx = OperationContext(scope=A, actor="ana", permissions=frozenset({"demo.view"}), language=language)
    outcome = assistant.tools.run(ctx, figures, "{}")
    assert outcome.outcome == "ok"
    return json.loads(outcome.content)


@HUB_DB
@pytest.mark.parametrize(
    ("country", "language", "revenue", "price"),
    [("ES", "es", "3,60\xa0€", "950\xa0JPY"), ("ES", "en", "€3.60", "¥950"), ("JP", "es", "360\xa0JPY", "950\xa0JPY")],
)
def test_an_amount_is_told_as_the_screens_write_it_in_the_business_currency_or_its_records(country, language, revenue, price):
    """hub#2603: a bar in Spanish heard «1.50 EUR» for the «1,50 €» on Inventory: the model repeats an amount as it reads
    it, so it reads it as the screens write it in the person's language, in the currency of its record or else the
    business's."""
    Hub.objects.update_or_create(slug=A.key, defaults={"name": "Bar A", "country": country})
    assert told(language) == {"revenue": revenue, "price_list": {"currency": "JPY", "price": price}}


@HUB_DB
def test_without_its_business_on_the_registry_an_amount_is_told_in_euros_as_its_card_paints_it():
    Hub.objects.filter(slug=A.key).delete()
    assert told()["revenue"] == "3,60\xa0€"
