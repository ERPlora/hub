"""Every amount a tool answers carries its mark: the model reads an amount in its currency only by that mark.

A tool's result reaches the model as the screens write it (``live.assistant.run_tool`` with ``money``), but the model
never sees the result's schema: an amount without the mark goes in cents, and the model repeats the figure as it
reads it (360 told as «360,00 €»).
"""

from live.operations import Operation
from ninja import Field, Schema

from base.tests.test_assistant_card_values_amounts import (
    MONEY,
    data_of,
    is_marked_amount,
    looks_like_an_amount,
    priced,
    tools,
)


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
