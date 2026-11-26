"""Nothing new is sold at 0 because nobody said its price: in every write the assistant calls, an amount named ``price``
is one the person says (its tool requires it, so the assistant asks for it before the card when it was not said, and
free is said as 0) or one that, left out, keeps what there was (an edit). Never a figure the write takes in silence."""

from live import assistant as shared
from live.assistant.fields import is_money
from live.operations import Operation, registry
from ninja import Field, Schema

from base import assistant

PRICE = "price"


def silent_prices(op: Operation) -> list[str]:
    """The amounts named ``price`` of ``op``'s input, at any depth, that a write takes as a figure when left out."""
    schema = shared.input_schema(op)
    found: list[str] = []
    _walk(schema, schema.get("$defs", {}), "", found)
    return found


def _walk(prop: dict, defs: dict, path: str, found: list[str]) -> None:
    prop = shared.resolved(prop, defs)
    required = set(prop.get("required", ()))
    for name, inner in prop.get("properties", {}).items():
        datum = shared.resolved(inner, defs)
        where = f"{path}{name}"
        if name == PRICE and is_money(datum) and name not in required and datum.get("default") is not None:
            found.append(where)
        _walk(datum, defs, f"{where}.", found)
    items = prop.get("items")
    if isinstance(items, dict):
        _walk(items, defs, f"{path.rstrip('.')}[].", found)
    for option in (*prop.get("anyOf", ()), *prop.get("oneOf", ())):
        _walk(option, defs, path, found)


def writes() -> list[Operation]:
    return [op for op in registry.values() if op.kind == "command" and assistant.tools.is_tool(op)]


def test_no_write_of_the_assistant_prices_something_at_a_figure_nobody_said():
    silent = {op.name: found for op in writes() if (found := silent_prices(op))}
    assert silent == {}


class LineIn(Schema):
    price: int = Field(0, json_schema_extra={"money": True})


class SilentIn(Schema):
    name: str
    price: int = Field(0, json_schema_extra={"money": True})
    lines: list[LineIn] = []


class SaidIn(Schema):
    name: str
    price: int = Field(json_schema_extra={"money": True})


class KeptIn(Schema):
    price: int | None = Field(None, json_schema_extra={"money": True})


def a_write(input: type[Schema]) -> Operation:
    return Operation(
        name="demo.item.create",
        kind="command",
        permission="demo.manage",
        input=input,
        output=input,
        expose_api=False,
        ai={"description": "Create an item."},
        fn=lambda ctx, data: data,
    )


def test_the_check_finds_a_price_taken_in_silence_at_any_depth_and_lets_a_said_or_kept_one_pass():
    assert silent_prices(a_write(SilentIn)) == ["price", "lines[].price"]
    assert silent_prices(a_write(SaidIn)) == []
    assert silent_prices(a_write(KeptIn)) == []
    assert any(op.name == "inventory.product.create" for op in writes())
