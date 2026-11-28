"""What the card of a write says of a datum beyond its value, as the datum's screen says it: each datum as the write
takes it (``as_taken``), never one of our ids, a value that means there is no limit (``NO_LIMIT``), a figure with
decimals as the person's language writes it and a price with the unit it is for (``PER_UNIT``). The marks are declared
on the datum's schema, as its other marks are (``base.schemas.assistant.no_limit`` and ``per_unit``)."""

import re
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Annotated, Any

from babel.numbers import format_decimal
from django.utils import translation
from django.utils.translation import pgettext
from live import assistant as shared
from live.assistant import CHOICE
from live.operations import Operation
from pydantic import Field, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from base.business import babel_locale

#: The mark of a whole number one of whose values means there is no limit (``{"no_limit": 0}``, a maximum of 0): the
#: card says «No limit» for it, never the figure.
NO_LIMIT = "no_limit"

#: The mark of an amount that is a price for a unit (``{"per_unit": {"units": [...], "quantity": ..., "each": ...}}``):
#: the data of its own object that name the unit, the first one sent; the datum that says how many of it; and the unit
#: that is just «each one». The card names it «Price per kg» or «Price per 100 g», as the till writes «45,00 € / kg».
PER_UNIT = "per_unit"


def as_taken(op: Operation, arguments: dict) -> dict:
    """``arguments`` as ``op`` takes them, datum by datum: each one validated by its field and written as JSON writes it
    (a figure the model sent as a text is the number the write takes), or as sent when its field refuses it."""
    takers = _takers(op.input)
    return {key: _taken(takers.get(key), value) for key, value in arguments.items()}


@cache
def _takers(model: type) -> dict[str, TypeAdapter]:
    return {info.alias or name: _taker(info) for name, info in model.model_fields.items()}


def _taker(info: FieldInfo) -> TypeAdapter:
    """What validates a datum as its field does: its type with its constraints and validators, and the tag of its union."""
    tagged = [Field(discriminator=info.discriminator)] if info.discriminator is not None else []
    annotations = [*info.metadata, *tagged]
    return TypeAdapter(Annotated[info.annotation, *annotations] if annotations else info.annotation)


def _taken(taker: TypeAdapter | None, value: Any) -> Any:
    if taker is None:
        return value
    try:
        return taker.dump_python(taker.validate_python(value), mode="json", by_alias=True, exclude_unset=True)
    except ValidationError:
        return value


def marked(op: Operation, fields: list[dict], data: dict, language: str) -> list[dict]:
    """The ``fields`` of the card of ``op`` as their screens say them: none that is one of our ids (a record the card
    could not name), a value that means no limit in words and a price with its unit. ``data``: what the write takes."""
    schema = shared.input_schema(op)
    props, defs = schema.get("properties", {}), schema.get("$defs", {})
    with translation.override(language):
        return [
            _said(field, shared.resolved(props.get(field["name"], {}), defs), data, language)
            for field in fields
            if not (field["kind"] == "text" and shared.is_uuid(field["value"]))
        ]


def _said(field: dict, prop: dict, data: dict, language: str) -> dict:
    if NO_LIMIT in prop and type(field["value"]) is int and field["value"] == prop[NO_LIMIT]:
        return {**field, "kind": "text", "value": pgettext("base", "No limit"), CHOICE: True}
    if field["kind"] == "text" and _takes_a_fraction(prop) and _is_figure(field["value"]):
        # A figure says nothing of which datum it is: marked as a value of a closed list is, the screen names it.
        return {**field, "value": _number(Decimal(str(field["value"])), language), CHOICE: True}
    per = prop.get(PER_UNIT)
    unit = _unit(per, data, language) if field["kind"] == "money" and isinstance(per, dict) else None
    if unit is None:
        return field
    return {**field, "label": pgettext("base", "%(datum)s per %(unit)s") % {"datum": field["label"], "unit": unit}, "titled": True}


#: A figure as JSON and the text of a decimal write one («5.2», «-1.250»), as the write takes it.
_FIGURE = re.compile(r"-?\d+(?:\.\d+)?")


def _takes_a_fraction(prop: dict) -> bool:
    """Whether a datum takes a number that may carry decimals (a quantity, a percentage, a coordinate): a ``number``,
    or the number branch of a decimal; never a whole number, nor a text that looks like one (a phone, a postal code)."""
    return any(branch.get("type") == "number" for branch in prop.get("anyOf", []) or [prop])


def _is_figure(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int | float) or (isinstance(value, str) and _FIGURE.fullmatch(value) is not None)


def _number(value: Decimal, language: str) -> str:
    """``value`` as the screens write a quantity in ``language`` («5,2», «1.500,25»; «1,500.25» in English): every
    decimal it carries and none it does not need."""
    return format_decimal(value, locale=babel_locale(language), decimal_quantization=False)


def _unit(per: dict, data: dict, language: str) -> str | None:
    """The unit a price is for, as the till writes it («kg», «100 g»), or ``None`` when it is for each one."""
    unit = next((data[name] for name in per.get("units", ()) if isinstance(data.get(name), str) and data[name]), None)
    quantity = _quantity(data.get(per.get("quantity", "")))
    if unit is None or (unit == per.get("each") and quantity == 1):
        return None
    return unit if quantity == 1 else f"{_number(quantity, language)} {unit}"


def _quantity(value: Any) -> Decimal:
    """How many units a price is for: one unless the write takes another."""
    try:
        quantity = Decimal(str(value)) if value not in (None, "") else Decimal(1)
    except InvalidOperation:
        return Decimal(1)
    return quantity if quantity.is_finite() and quantity > 0 else Decimal(1)
